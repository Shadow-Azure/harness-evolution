# Bad Case 同步源工厂化设计：父类 + 工厂 + ClaudeUpstream 子类

[English](bugfix-bad-case-sync-source-factory-design.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-42
milestone: bugfix
depends: []
priority: P2
status: done
scope:
  - plans/fullstack-design/16-bad-case-sync-source-factory.md
  - plans/fullstack-design/README.md
  - .agents/**
adr:
  - ../../notes/proposed/architecture/2026-11-23-bad-case-sync-source-factory.md
github:
  number: 548
  url: https://github.com/Shadow-Azure/harness-evolution/issues/548
```

## 背景

bad case 有两条互相独立的来源线：接口上报（workspace 凭据 `POST /api/workspaces/{wid}/bad-cases`）与 global 源（上游接口同步：`HttpBadCaseCatalogSource` 目录分页 + `HttpSessionQuerySource` 两端点轨迹回填）。当前 global 线存在结构缺口：两个互不相干的 HTTP 客户端平级存在，没有共同父类与工厂；`BadCaseRootSyncService._sync_root()` 用内联 if/else 在 report/global 两条取数路径间切换（bad_case_sync.py:303-447）；main.py 用两段近似复制的过程式 if 块装配（main.py:270-325）；global 线 payload 的 runtime_key 落默认值 `"claude-code"` 硬编码（`_payload()`）；目录同步的 `on_duplicate_key_update` 对同 id 已上报行无条件覆盖上游字段（bad_case_catalog_sync.py:24-38,295-305），「已上报不重复同步」只在一半意义上成立。用户提出特性诉求：global 线做成工厂 + 父类 + 子类，bad case 获取与 session 获取全部走父类触发调用、子类实现，.env 配置后开启（未配置不开启），工厂按 .env 初始化子类，所有相关改动封装在子类内，session 处理复用既有 Session 解析父类/子类并新增子类实现。

## 目标

- 交付一份可链接的设计章节 `plans/fullstack-design/16-bad-case-sync-source-factory.md`（并登记进 `plans/fullstack-design/README.md` 索引），覆盖：现状与目标的差距分析、`BaseBadCaseSyncSource` 父类 / `BadCaseSyncSourceFactory` 工厂 / `ClaudeUpstreamBadCaseSyncSource` 子类的接口设计、解耦机制推演、目录同步与 root 同步两条数据流转的逐步 JSON 对照。
- 明确四条设计决策：① 代码标识符用 `BadCaseSync*` 命名族（不叫 `Global*`）；② 上报线与 global 线开关独立（global 开关仅被工厂在装配期读取，四种开关组合互不牵连）；③ 已上报 bad case 不被 global 目录同步覆盖（写者归属规则 + 跳过计数）；④ `_sync_root` 的 if/else 收敛为「冻结快照 → 统一 fetcher」的数据映射（`fetch_session()` 与既有 `SessionSourceFetcher` 协议同构）。
- 作为后续实现 issue 的设计依据：实现冲突时以本文档链接章节为准。

## 设计依据

- [§1 现状盘点](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s1)：两条来源的真实链路、global 线组件分工与逐文件证据（bad_case_sync.py / session_query / bad_case_query / main.py 行号）。
- [§2 差距分析](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s2)：七项目标要求与现状的逐条差距判定。
- [§3 目标设计](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s3)：新模块三件（父类/子类/工厂）、.env 开关 `HE_BAD_CASE_SYNC_PROVIDER` 与开关矩阵、`fetch_session` 模板方法与签名对齐、去重规则。
- [§4 解耦推演](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s4)：四类上游变更场景的改动局部性对照。
- [§5 目录同步数据流](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s5)：`fetch_bad_case_page` → `BadCasePage` → `CatalogCaseRow` → 去重跳过 → 落库的逐步 JSON。
- [§6 root 同步数据流](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s6)：源路由/冻结 → `fetch_session` → `SessionInfo` → payload → replay 解析的逐步 JSON。
- [§7 兼容与风险](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s7)：`SessionSourceSnapshot` 扩展（`extra="forbid"`）、行为兼容、测试影响面与实施顺序。

## 实现内容

- 新增 `plans/fullstack-design/16-bad-case-sync-source-factory.md`（第 16 章，纯设计文档，本 issue 唯一交付物）与 `plans/fullstack-design/README.md` 索引行。
- 新增 Agent Note 三件套 `.agents/notes/proposed/architecture/2026-11-23-bad-case-sync-source-factory.*`：记录命名（弃 `Global*` 用 `BadCaseSync*`）、if/else 收敛（弃保留骨架）、目录同步去重（弃无条件覆盖）三项决策与被否方案。
- 新增本 issue 三件套，挂 bugfix milestone（常驻桶），不新开 milestone。

## 实施步骤

1. 通读 `service/acquisition/bad_case_sync*.py`、`third_party_api/session_query|bad_case_query|session_source/`、`main.py` 装配段，核实现状行为（含 upsert 覆盖语义与冻结路由）。
2. 产出设计文档：差距分析 → 父类/子类/工厂设计 → 解耦推演 → 两条数据流转的 JSON 对照 → 兼容风险与实施顺序。
3. 按用户逐轮反馈修订：两线独立与开关矩阵、逐 root 源路由表述、已上报去重、`BadCaseSync*` 命名、挂 bugfix milestone。
4. 写 Agent Note，重录 i18n 配对，过流程与文档门禁，`flow:sync` 回填编号后提 PR。

## 依赖与交付边界

- 依赖：无（纯设计，不改任何生产代码）。
- 非目标：不改 `apps/api`、`apps/web`、`packages/contracts` 的任何代码；不建实现 issue；不新增数据库迁移；不新开 milestone。

## 独立验证

```sh
pnpm verify:flow; pnpm lint:docs
```

- 全绿；`verify-flow --diff origin/main` 对本 PR diff 的 scope 覆盖通过。

## 验收标准

- 设计文档覆盖用户全部特性诉求：工厂按 .env 初始化子类、未配置不开启、获取走父类触发/子类实现、改动封装子类、session 复用既有父/子/工厂并留新增子类挂点。
- 文档含两条数据流转的逐步说明：每步给出处理类.函数与输入/输出 JSON 形态。
- 文档明确两线独立（开关矩阵四种组合）、已上报 bad case 的写者归属与跳过规则、`_sync_root` if/else 的收敛方案。
- Agent Note 双语配对完整，记录三项关键决策及被否方案。

## 门禁与 CI

- `pnpm verify:flow`：issue 三件套、状态机与 scope 覆盖。
- `pnpm lint:docs` / `pnpm verify:docs`：Agent Note 配对与文档门禁。
- 纯文档改动，不触发 API/Web 构建与测试 lane 的行为变化。

## 非目标

- 不实现 `bad_case_sync_source/` 模块或任何同步服务改造。
- 不改接口上报线行为；不动 DB 快照 `kind="global"` 数据标签。
- 不在本 issue 内裁决实现 issue 的排期与切分。
