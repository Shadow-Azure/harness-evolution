# 优化 trajectory_payloads 存储：压缩、对象存储分层与回源边界

[English](m29-payload-tiered-storage.en.md) | 中文

```yaml flow
kind: issue
id: m29-01
milestone: m29
depends: []
priority: P1
status: ready
scope:
  - apps/api/app/db/**
  - apps/api/app/service/acquisition/**
  - apps/api/app/service/evolution/**
  - apps/api/app/config.py
  - apps/api/alembic/versions/**
  - apps/api/tests/**
  - deploy/**
  - docs/**
  - .env.example
  - .agents/**
  - plans/**
  - scripts/**
adr: []
github:
  number: 654
  url: https://github.com/Shadow-Azure/harness-evolution/issues/654
```

## 背景

### 现状

`trajectory_payloads` 的 `payload` 是 `LONGTEXT`，每个 agent（主 agent 或子 agent）一行，保存该 agent 的原始 JSONL 全文；同一行的 `content_hash` 是 payload 的 SHA-256，`source_type` 记录 `script` / `http_api` 接入通道。设计事实见 [06 §3.0](../../../plans/fullstack-design/06-database-design.md) 与 [06 §6](../../../plans/fullstack-design/06-database-design.md)，表结构见 `apps/api/app/db/models/domain.py` 的 `trajectory_payloads`。

生产是阿里云单机：nginx、uvicorn 与 MySQL 8 同机，系统盘 40GB；见 [部署文档](https://github.com/Shadow-Azure/harness-evolution/blob/main/docs/deployment.md) 与 [阿里云手册](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/deploy-aliyun-playbook.md)。容量估算为 10³–10⁴ 行（[06 §6](../../../plans/fullstack-design/06-database-design.md)）；仓库里的原型样本是 4 个真实主会话家族、64 个 rollout、25,170 条记录、约 72.2MB（[Session family 原型记录](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/proposed/architecture/2026-10-19-session-family-prototype.md)），折合约 1.1MB/行，外推到 10³–10⁴ 行约为 1–11GB 原始文本。这是当前最大的表，且没有 retention 或删除路径。

读路径只有两类：归一化重放按待处理条件读取 payload（`list_pending_payloads`），本地归因与按 root 重放读取一个 root 的全部 payload（`list_root_payloads`）；归一化后的业务表不保存消息与内容块，需要原文时按 `(runtime_key, root_session_id, agent_id)` 回读。也就是说，归一化完成后 payload 基本是冷数据，但 parser 升级会再次触发重放。相关代码在 `apps/api/app/db/crud/acquisition_replay.py`、`apps/api/app/service/acquisition/replay.py` 与 `apps/api/app/service/evolution/local_attribution.py`。

写入路径有三条：第三方脚本 upsert（`script`）、上游 pull（`http_api`）与 bad_case 根会话同步（`http_api`）。当前没有 payload 删除任务；payload 缺失时归一化层会保留业务数据并记录日志（`list_missing_payload_sources`），这是分层后“对象缺失”可以复用的兼容缝。

### 诉求

- 降低 `trajectory_payloads` 对 MySQL 空间的占用，避免主库随历史 Session 无限增长。
- 评估“只保存下载方式或引用，低频时再回源下载”的可行性，而不只做数据库内压缩。
- 参考成熟方案与高 star 开源项目，给出推荐方案、代价、风险和参考来源。
- 先把选型写在 issue 里讨论；确认后再进入实现，不在本 issue 直接改代码。

## 目标

- 在不丢失原始证据、不改变归一化与重放语义的前提下，把 payload 从主库热数据中剥离：先压缩，再把低频 payload 分层到对象存储。
- `trajectory_payloads` 仍是原始轨迹的唯一事实源；按 `(runtime_key, root_session_id, agent_id)` 回读、按 `content_hash` 幂等重放、parser 版本升级重放的语义不变。
- 同一份 payload 只保留一个逻辑副本（主库或对象存储之一），不做“主库一份、对象存储再一份”的长期双写。
- 上游回源只作为对象存储缺失时的可选恢复路径，不作为唯一副本；`script` 来源不得依赖回源。
- 给出可度量的容量、读延迟、失败处理与回滚验收口径，数值在只读测量后确定。

## 设计依据

- [06 §3.0 `trajectory_payloads`](../../../plans/fullstack-design/06-database-design.md)：payload 列、主键、`content_hash`、`source_type` 与“本服务只读”的边界。
- [06 §6 索引与容量估算](../../../plans/fullstack-design/06-database-design.md)：`trajectory_payloads` 为 10³–10⁴ 行，payload 占主要体积。
- [01 §6 部署形态与扩展路径](../../../plans/fullstack-design/01-architecture.md)：单机 MySQL 与服务同机，没有独立的对象存储层。
- [07 §2 原始轨迹接入与归一化](../../../plans/fullstack-design/07-backend-implementation.md)：待处理判定、pull 落 payload、根会话原子重放。
- 代码现状：`apps/api/app/db/models/domain.py` 的 `trajectory_payloads`；`apps/api/app/db/crud/acquisition_replay.py` 的 `list_pending_payloads` / `list_root_payloads`；`apps/api/app/third_party_api/trajectory/http.py` 的 `fetch(session_id)` 回源入口。
- 容量样本：[Session family 原型记录](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/proposed/architecture/2026-10-19-session-family-prototype.md) 的 64 rollout / 72.2MB。

## 方案对比

| 方案 | 主库降幅 | 保留原文与重放 | 主要代价与风险 | 结论 |
|---|---|---|---|---|
| A. 应用层 zstd 压缩 | 约 3–5x，待实测 | 是 | 需要迁移与回填；读写多一次压缩/解压 CPU；仍随数据量线性增长 | 第一阶段先做 |
| B. 对象存储分层（claim check） | 主库只剩元数据与热窗口，约 90%+ | 是 | 新增 OSS 依赖、网络读延迟、对象生命周期与备份/恢复流程 | 第二阶段推荐 |
| C. 只存下载引用，按需回源 | 接近 100% | 仅 `http_api` 可，且依赖上游 | `script` 无法回源；上游保留期/可用性/内容稳定性不可保证；批量重放会退化为大量网络请求 | 默认只作恢复；上游书面保证存档时见 C+ |
| D. MySQL 原生页压缩 | 通常低于 A | 是 | MySQL 8.0 只支持页级 Zlib/LZ4，需要稀疏文件与 hole punching，作用于整表/索引，调优空间小 | 不作为主方案 |
| E. 独立归档库或冷表 | 部分 | 是 | 多一套数据库运维；成本不优于对象存储；查询链路更复杂 | 不推荐 |

### A. 应用层压缩

把 payload 以 zstd 压缩后存入同一个逻辑列，新增 codec 与字节数元数据；写入时压缩，读取时解压，`content_hash` 仍对原始文本计算。优点是改动局部、SQLite/MySQL 双方言一致、可与后续对象存储复用同一套编码；缺点是要做一次历史数据回填，并接受压缩/解压 CPU。zstd 的字典与长窗口适合 JSONL 这种键名高度重复的文本，但实际压缩比必须用生产样本测量，不能把压缩比当成验收前提。

### B. 对象存储分层

采用 claim check 模式：payload 对象上传到对象存储，`trajectory_payloads` 只保留 identity、hash、codec、字节数与对象键；读路径按对象键取回、校验 hash、解压。主库不再承载历史 payload 的体积，`mysqldump`、DDL 与磁盘压力随之下降。代价是对象存储成为新的持久依赖，必须补上私有桶、生命周期、版本/备份、缺失与损坏诊断；读延迟从本地行读取变成一次对象 GET，需要缓存或热窗口控制。

### C. 只存引用并按需回源

这是提出人最初提到的方向：不保存 payload，只保存 `(runtime_key, root_session_id, agent_id)` 与上游地址，低频访问时再下载。它把“存什么”变成“怎么取”，在理想条件下最省主库空间。

**优势**

- 主库降幅最大：行内只留 identity、hash、`source_type` 与少量元数据，payload 字节数归零；不需要对象存储 bucket、生命周期和额外备份。
- 复用现有回源入口：`HttpTrajectorySource.fetch(session_id)` 已经存在，pull 与 bad_case 同步也走同一契约，不需要新增存储服务。
- 单一副本、责任清晰：原始轨迹仍由上游持有，本服务不承担第二份大文本的加密、备份和删除；retention 交给上游。
- 对“只关心最近会话”的场景足够：如果业务只回看近期会话，且上游保留期覆盖这个窗口，C 的读路径可以接受。

**劣势与风险**

- 覆盖不全：只对 `source_type = http_api` 成立；第三方脚本写入的 `script` 行没有上游地址，仍必须存在主库或对象存储。C 不能作为全表方案。
- 上游不是存档：契约是本服务定义的客户端契约，不是上游承诺的长期保留；404/410、保留期到期、租户删除都会让原文永久不可得，归一化表虽在，证据与 parser 升级重放失去源。
- 内容可能漂移：重新下载可能带回新增事件或被截断的历史；`content_hash` 不一致时，拒绝会让重放失败，接受会改写既有归一化结果，必须额外定义版本或冲突策略。
- 重放成本高：parser 升级会触发大批 pending 行重放，C 把一次数据库扫描变成 N 次上游请求；429、超时、并发上限与部分失败会让重放变慢且不确定。
- 读延迟与可用性：每次冷读或归因都要一次网络 GET，上游故障直接变成证据不可用；要缓存就回到“第二份副本”，与 C 的省空间目标冲突。
- 安全与审计：payload 离开本服务存储，访问控制、脱敏边界、删除审计和合规保留都更依赖上游；本服务难以证明“这条证据当时是什么”。

**流程示例（`http_api` 根会话 S，主 agent + 1 个子 agent）**

1. 写入：bad_case 同步调用 `fetch(S)` 拿到主 agent 与子 agent 的 JSONL，计算 `H_main`、`H_sub`，只写 `trajectory_payloads` 的 identity、`content_hash`、`line_count`、`source_type=http_api`；不写 payload。
2. 读取：归一化或归因按 `(claude-code, S, main)` 找到行，`load_payload` 发现没有本地 payload，调用 `fetch(S)` 取回整包。
3. 校验：分别计算主 agent 与子 agent 的 SHA-256；与行内 hash 一致才归一化。子 agent 缺失或 hash 不一致时，只隔离该 root，保留已归一化数据并记录诊断。
4. 重放：parser 升级后，调度器列出所有 pending root；对每个 root 回源，限制并发（例如 4）并重试；N 个 root 就是 N 次上游请求，任一失败只影响该 root。
5. 失败：上游返回 404/410 或保留期已过，行仍在但 payload 永久不可用；读取方返回“来源已过期”的稳定诊断，不能伪造空内容；若要恢复，只能依赖上游重新提供或之前的备份。

**如果上游能保证存档（C+）**

“保证存档”必须落成可验收条款，而不是口头承诺：

- 保留期与删除：至少覆盖本服务的证据与重放窗口；到期前通知，支持 legal hold；租户删除有审计。
- 不可变版本：同一 `session_id` 可按版本取回；同一版本字节稳定，`content_hash` 不漂移；新增事件产生新版本，不覆盖旧版本。
- 可用性与 SLA：读接口有明确可用性、错误预算和维护窗口；故障时本服务能区分“上游不可用”和“原文不存在”。
- 批量导出与配额：parser 升级需要按时间窗或租户批量导出，而不是逐 root 做 N 次 `fetch`；给出 QPS、并发与单次大小上限。
- 权限与审计：本服务只能读自己租户；上游记录访问审计；凭据最小权限并可轮换。
- 成本与退出：请求与 egress 计费可预测；合同终止时可导出全量原文。

如果这些条件都成立，C+ 可以把 `http_api` 的原始 payload 从本服务完全移出，主库只保留 identity、版本、hash 与 `line_count`；读路径按 `(session_id, version)` 取回并校验，不再需要对象存储。此时 C+ 可以作为 `http_api` 的主方案，而不是只做恢复。

即便如此，仍有三件事不会自动消失：

1. `script` 行没有上游，必须继续用 A/B（压缩或对象存储）；除非所有写入方都改为 `http_api`，否则 C+ 只能覆盖一部分表。
2. 重放仍需批量能力：没有批量导出时，parser 升级会把 N 个 root 变成 N 次回源；需要上游提供按时间窗或租户的导出，或在本服务保留一个可重放的紧凑副本（那就回到 A/B）。
3. 读可用性与审计依赖上游：上游故障时证据不可读；若要求“上游挂了也能看历史证据”，C+ 不成立；要加缓存就回到第二份副本。

**结论**：上游书面保证“保留期 + 不可变版本 + 可用性 + 批量导出 + 审计与退出”，且所有来源都走 `http_api` 时，C+ 可以作为主方案，优先于对象存储；否则仍推荐 A → B，C/C+ 只作恢复路径。若只有部分来源可保证，采用“C+ 覆盖 `http_api` + A/B 覆盖 `script`”的混合。

### D. MySQL 原生页压缩

MySQL 8.0 的 `COMPRESSION` 是 InnoDB 页级压缩，支持 Zlib/LZ4，依赖稀疏文件与 hole punching，作用于整表与索引；它不是列级压缩，也不适合只压缩 payload 这一列。它能减少磁盘占用，但压缩比、文件系统支持与对 buffer pool 的影响都不可控，且无法与对象存储分层复用。作为过渡手段可以评估，不作为推荐主方案。

### E. 独立归档库或冷表

把历史 payload 搬到另一套数据库或冷表，能缓解主库压力，但没有解决“大文本不该放在事务库”的根因；多一套数据库的备份、监控与恢复成本，通常高于对象存储。除非已有现成的归档基础设施，否则不推荐。

## 实现内容

推荐按 A → B 两阶段落地；C 默认只作恢复路径，若上游书面保证存档且覆盖全部来源，按 C+ 评估是否升级为主方案；D/E 不采用。以下为推荐方案的设计口径，选型确认后把本 issue 推进到 in-progress，再拆实现。

### 阶段 1：payload 压缩

- `trajectory_payloads` 增加 `payload_codec`（`raw` / `zstd`）与 `payload_bytes`（原始字节数）；`payload` 改为二进制列（MySQL `LONGBLOB`、SQLite BLOB），新写入默认 zstd，读取按 codec 解压。`content_hash` 仍对解压后的原始文本计算，重放与幂等判定不变。
- 历史行分批回填：每批按主键范围取数、压缩、写回，记录进度；回填失败可重试，已压缩行按 codec 跳过。若生产 `ALTER TABLE` 的锁或重建时间不可接受，改用影子列 `payload_zstd` + 双读，待回填完成后的下一个 release 再删旧列。
- 压缩参数从 zstd level 3 起步，按 CPU 与压缩比测量结果调整；不在业务请求路径做高 level 压缩，回填任务可以更慢。
- 读路径统一走一个 `decode_payload(row)` 帮助函数，避免调用方各自判断 codec；旧 `raw` 行继续可读，保证滚动发布期间新老版本共存。

### 阶段 2：对象存储分层

- `trajectory_payloads` 增加 `payload_object_key`（可空），`payload` 允许为空；一行必须且只能有“主库 payload”或“对象键”之一。对象键使用内容寻址：`payloads/{runtime_key}/{root_session_id}/{agent_id}/{content_hash}.jsonl.zst`，同一内容重复上传幂等，便于校验与清理。
- 离线任务选择 `updated_at < now - HE_PAYLOAD_OFFLOAD_AFTER_DAYS`、已归一化（`source_records.processed_hash = content_hash`）且 `payload` 非空的行；先上传并校验对象可读，再在事务里写 `payload_object_key`、清空 `payload`。上传成功但事务失败只会留下孤儿对象，由生命周期规则清理，不会造成“数据库已删、对象不存在”。
- 读路径：有主库 payload 直接解压；只有对象键时 GET 对象、校验 `content_hash`、解压；对象缺失或 hash 不匹配返回稳定诊断，不把空内容当成合法 payload。重放仍按 root 隔离，单个 root 的对象失败不拖垮整批。
- 批量重放不能一次把所有待处理 payload 拉进内存：按 root 或 runtime 分页取 identity，限制并发对象 GET 数量，逐 root 读取与归一化；parser 升级触发的全量重放也要遵守这个上限。
- 对象存储优先使用阿里云 OSS（S3 兼容、与 ECS 同地域、私有桶、服务端加密、版本与生命周期）；开发与测试用本地文件系统实现同一个 `PayloadObjectStore` 接口，CI 不访问云。配置通过 `HE_PAYLOAD_OBJECT_*` 注入，凭据只放环境变量，不写仓库与日志。
- 备份与恢复：主库 dump 不再包含 payload，对象存储的版本/生命周期与恢复步骤必须写进部署文档；需要提供按 `(runtime_key, root_session_id, agent_id)` 或对象前缀的恢复命令。

### 回源的适用边界

- 只有 `source_type = http_api` 的行有回源入口（`HttpTrajectorySource.fetch(session_id)`）；`script` 行没有上游地址，必须在对象存储里保有持久副本。
- 回源只在上游明确保留该会话、且返回内容的 `content_hash` 与行内记录一致时接受；hash 不一致视为内容已变化，不能静默覆盖既有归一化结果，应记录诊断并走人工/重放决策。
- 回源要考虑 404/410、429、超时、上游版本漂移与批量重放的请求量；它适合单会话恢复，不适合作为 parser 升级后的全量重放通道。
- 如果未来 OSS 成本成为主要矛盾且上游给出保留期承诺，可以增加“对象保留 N 天后删除、按需回源”的策略；这属于可选的阶段 3，默认关闭，且必须保留 hash 与失败诊断。

## 实施步骤

1. 只读测量生产数据：行数、`SUM(LENGTH(payload))`、payload 大小的 p50/p95、按 runtime/source_type/updated_at 的分布；用脱敏样本测量 zstd 压缩比，不把 payload 内容写入仓库或 issue。
2. 根据测量结果确定阶段 1 的压缩比目标、回填批次与 `ALTER TABLE` 方案；确认对象存储的 region、bucket、私有 ACL、加密、生命周期和备份责任人。
3. 实现阶段 1：schema 迁移、codec、批量回填、双读与解码帮助函数；补单元/集成测试，验证旧 `raw` 行与新 zstd 行都能重放。
4. 实现阶段 2：对象存储接口与本地实现、上传/校验/offload 任务、读路径回退、缺失与 hash 不匹配诊断、恢复命令；补 fake object store 测试。
5. 在 staging 用 fixtures 与一份脱敏真实样本跑归一化、重放、归因与恢复；记录主库字节数、对象 GET 延迟与失败率；再按开关灰度到生产。
6. 观察一个 retention 周期后，再决定是否启用阶段 3 的“删对象、按需回源”；没有上游保留期承诺就不启用。

## 依赖与交付边界

- 代码依赖：无。阶段 1 可独立交付；阶段 2 需要对象存储 bucket、region 与凭据，属于部署前置条件。
- 交付边界：只改 payload 的存储、读取与迁移，不改变归一化规则、业务表结构、现有 API 的语义与上游轨迹契约；不新增第二个逻辑副本；不在没有持久副本时删除历史 payload。
- 阶段 1 与阶段 2 可以分成两个 issue/PR；本 issue 先完成选型与设计，确认后再拆实现，避免把“讨论”和“实现”混在一个 PR。
- 待决问题：压缩列采用原地改类型还是影子列；对象存储用 OSS 还是自建 MinIO（同盘 MinIO 不解决 40GB 磁盘问题，故倾向 OSS）；热窗口与 retention 天数；是否为审计保留明文副本（倾向不保留，靠 hash + 解码校验）。

## 独立验证

本 issue 只定义验收口径，不声称已有实现或测试。实现 PR 必须新增并运行以下验证：

```sh
pnpm verify:flow
pnpm lint:docs
pnpm verify:docs
pnpm lint:api
pnpm typecheck:api
pnpm test:api
pnpm test:db:mysql
pnpm test:gates
```

- 阶段 1：codec 往返测试覆盖 `raw` 与 `zstd`；迁移测试覆盖 SQLite/MySQL；同一 fixture 在改动前后重放，业务表行数与内容逐字段一致；SQL 断言 `payload IS NULL` 且 `payload_object_key IS NULL` 的行数为 0。
- 阶段 2：fake object store 覆盖上传、读取、缺失、hash 不匹配；offload 先上传后清空，重复执行幂等；模拟“上传成功、事务失败”后重试不丢数据；按 root 重放在对象失败时只影响该 root。
- 容量验证：记录改动前后 `SUM(LENGTH(payload))`、表总大小与对象存储总量；用同一批样本比较压缩比与 p95 读取延迟。具体阈值在测量后写入本 issue 的验收标准，不先写死。

## 验收标准

- 阶段 1：在代表性样本上，主库 payload 字节数相对原始文本下降至少 60%（最终阈值以测量为准）；历史 `raw` 行与新增 `zstd` 行都能被同一套重放读取；归一化结果与改动前一致；滚动发布期间新旧版本可共存。
- 阶段 2：超过热窗口且已归一化的 payload 不再存放在主库；主库增长与历史 Session 数量解耦；对象读取、hash 校验、缺失诊断与恢复命令都有测试；上传/事务中断不会造成数据丢失。
- 运维：对象存储的备份/恢复、生命周期、监控与告警有文档；主库 dump 与恢复流程同步更新；失败率与读延迟有可观测指标。
- 选型：本 issue 记录最终选择、放弃项与理由；确认后把状态推进到 in-progress，并把实现拆成可独立验收的 issue/PR。

## 门禁与 CI

- 本 issue 的流程文件改动：`pnpm verify:flow`、`pnpm lint:docs`、`pnpm verify:docs`。
- 实现 PR：`pnpm lint:api`、`pnpm typecheck:api`、`pnpm test:api`、`pnpm test:db:mysql`、`pnpm test:gates`；不预期改 OpenAPI，若改接口再跑 `pnpm contract:check`。
- MySQL lane 必跑：只在 SQLite 上验证不足以覆盖 `LONGTEXT`/`LONGBLOB`、页压缩与迁移行为。
- 本改动不改 UI，不需要前后端截图对比；若后续进入证据查看界面，再按 UI 规则补 Before/After。

## 非目标

- 不采用“只存下载引用、不保留任何本地副本”作为主方案；不把上游回源当成唯一存储。
- 不删除没有持久副本的历史 payload；不以节省空间为由丢失原始证据或重放能力。
- 不改变归一化算法、业务表结构、现有 API 语义与上游轨迹契约。
- 不做与存储无关的 UI、产品改版或数据库引擎迁移。
- 不把 MySQL 页压缩或独立归档库作为首选方案；不在本 issue 直接写实现代码。

## 参考来源

以下项目与文档提供了“大 payload 移出事务库、热冷分层、按引用取回”的成熟做法；star 数为 2026-11-27 通过 GitHub API 读取的近似值。

- [Temporal External Storage](https://docs.temporal.io/external-storage)：claim check 模式，超过阈值的 payload 上传到 S3 等外部存储，工作流只传引用；覆盖阈值、并行上传/下载与 UI 展示引用。约 24.6k stars。
- [Azure Architecture Center: Claim Check pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/claim-check)：把大 payload 放外部存储、消息只传引用；明确列出生命周期归属、可用性与持久性、读取延迟、写入与引用的一致性、完整性校验等约束，正好对应本 issue 的风险清单。
- [Langfuse Architecture](https://langfuse.com/handbook/product-engineering/architecture)：Postgres 存事务数据、ClickHouse 存 trace/observation、S3/Blob 存事件与附件；是“分析库 + 对象存储”分离的相近形态。约 37.9k stars。
- [Grafana Tempo: Object storage](https://grafana.com/docs/tempo/latest/reference-tempo-architecture/object-storage/)：所有 trace 数据长期放对象存储（S3/GCS/Azure），本地文件系统只用于开发测试；说明对象存储作为 trace 长期后端的可行性、成本与读路径。约 5.6k stars。
- [Apache Kafka Tiered Storage (KIP-405)](https://cwiki.apache.org/confluence/display/KAFKA/KIP-405%3A+Kafka+Tiered+Storage)：本地 tier 保留近期数据、远端 tier 放 S3 等对象存储，按 retention 分离热冷；是“热窗口 + 冷对象”的直接参考。约 34.4k stars。
- [MinIO](https://github.com/minio/minio)：高 star 的 S3 兼容对象存储，适合自建或本地验证；但部署在同一块 40GB 系统盘上不解决磁盘问题，生产更倾向同地域 OSS。约 61.2k stars。
- [facebook/zstd](https://github.com/facebook/zstd)：高压缩比、解压快的通用压缩算法，适合 JSONL 文本；本方案阶段 1 的编码基础。约 28.3k stars。
- [MySQL 8.0 InnoDB Page Compression](https://dev.mysql.com/doc/refman/8.0/en/innodb-page-compression.html)：MySQL 原生页级压缩（Zlib/LZ4）的官方说明，用于对比方案 D 的能力边界。
- [阿里云 OSS](https://www.aliyun.com/product/oss)：生产同地域的对象存储选项，提供私有桶、服务端加密、版本与生命周期；具体 bucket/费用以部署环境为准。
