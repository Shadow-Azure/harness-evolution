# Agent Note: Bad Case 同步源工厂化——父类、工厂与 ClaudeUpstream 子类

Status: implemented

[English](2026-11-23-bad-case-sync-source-factory.en.md) | 中文

## Problem

bad case 的 global 源线在代码里不是「一个源」，而是两个互不相干的 HTTP 客户端（`HttpBadCaseCatalogSource` 目录分页、`HttpSessionQuerySource` 两端点轨迹回填）、`main.py` 两段近似复制的装配 if 块，以及 `BadCaseRootSyncService` 里两套几乎同构的 BFS 循环的总和。它造成三个具体缺口：`_sync_root` 用内联 if/else 在 report/global 两条取数路径间切换，global 路径完全绕开既有 `SessionSourceFactory` / `BaseSessionSourceAdapter` 投影链，`runtime_key` 靠 `LocalAgentPayload` 的默认值兜底；启用与否由两组端点凭据隐式决定，没有一个「配置后开启、未配置不开启」的显式开关；目录同步对同 id 的已上报行无条件 `ON DUPLICATE KEY UPDATE` 覆盖 13 个上游列（含 `created_at`，而 report 源选择正按 `created_at` 排序），并把它们全部计入 `updated`——「已上报不重复同步」只在一半意义上成立。

用户的诉求是特性性的：global 线做成工厂 + 父类 + 子类，bad case 获取与 session 获取全部走父类触发调用、子类实现，`.env` 配置后开启，所有上游差异封装在子类内，session 处理复用既有 Session 解析父类/子类并新增子类实现。完整设计见 [plans/fullstack-design/16 · bad case 同步源工厂化](../../../../plans/fullstack-design/16-bad-case-sync-source-factory.md)；本 Note 只记录三项取舍与被否方案。

## Decision

**命名：代码标识符用 `BadCaseSync*` 族，不叫 `Global*`。** 新模块 `third_party_api/bad_case_sync_source/` 三件：`BaseBadCaseSyncSource`（父类，模板方法 `fetch_bad_case_page` / `fetch_session`）、`ClaudeUpstreamBadCaseSyncSource`（子类）、`BadCaseSyncSourceFactory`（工厂，按 `HE_BAD_CASE_SYNC_PROVIDER` 装配期实例化一次，未配置返回 `None`，未知值启动失败）。「global」在代码里已经是 DB 快照标签（`bad_case_root_sync.source_kind = "global"`）与 per-root 路由状态的词，若再用它命名可替换的实现，会把「路由到哪」与「由谁取数」两件事绑死。

**`_sync_root` 的 if/else 收敛为「冻结快照 → 统一 fetcher」的数据映射，不保留两条分支骨架。** `fetch_session(*, session_id, expected_parent_id, snapshot)` 与既有 `SessionSourceFetcher.fetch` 同构，两者都返回 `SessionInfo`；映射表只有 `"report"` / `"global"` 两项，循环体只有一个。global 子类把两端点结果合成为 `SessionSourceEnvelope`，再经既有 `SessionSourceFactory.create(runtime).project` 投影——与 report 路径走同一条链，`_payload()` 删除，`runtime_key` 由子类显式声明。

**已上报 bad case 不被目录同步覆盖：写者归属 + 跳过计数，弃无条件覆盖。** `bad_cases` 新增 `origin ∈ {report, catalog}`，由首次写入者决定；目录同步只更新 `origin = "catalog"` 的行，`origin = "report"` 的行跳过并计入 `skipped`。上报线插入时写 `report`，重报不改归属。

## Alternatives considered

- **命名为 `GlobalBadCaseSource` / `GlobalSourceFactory`**：与用户的口头说法一致，但「global」已是路由状态词；一旦出现第二个上游，`Global` 既不能表达「哪一个」，又会与 `kind="global"` 快照标签混淆。否决。
- **保留 `_sync_report_root` / `_sync_global_root` 骨架，只把 HTTP 调用收进子类**：改动最小，但两套 BFS 循环（deadline、limits、续租、入队）继续重复，新增上游仍要加第三套循环；父类模板方法的价值恰恰在于让服务层只认一种 fetcher。否决。
- **`fetch_session` 返回 `SessionTrajectory` + children 元组，由服务层拼 payload**：子类更薄，但服务层要同时认 `SessionInfo`（report 路径）和元组（global 路径），同构性消失，if/else 只是换了位置。否决。
- **目录同步改为纯 insert-if-absent（已存在一律不更新）**：零迁移即可保护已上报行，但目录自有行也从此冻结，上游对标题/描述的修订永不传播；写者归属只多一列，换来两类写者各自正确的更新语义。否决。
- **用 `workspace_id ≠ DEFAULT_WORKSPACE_ID` 或 `session_source IS NOT NULL` 推断写者，不加列**：无迁移，但上报到默认 workspace 且不带 `sessionSource` 的行会被误判为目录自有，缺口只是缩小没有关闭；游标式同步使回填误差的实际暴露面接近零，显式列的代价很低。否决。
- **未配置 `HE_BAD_CASE_SYNC_PROVIDER` 时由旧端点凭据隐式推断开启**：现网零改动，但「未配置不开启」不再成立，开关矩阵从两种状态退化为三种；改为装配期 warning 提示部署补一行。否决。
- **为 global 路径注册第二个 `runtime_key = "claude-code"` 的 `BaseSessionSourceAdapter` 子类**：形式上满足「新增子类实现」，但 `SessionSourceFactory.register` 按运行时键拒绝重复，且同一运行时不应有两套元数据 schema；新增子类的挂点是「新运行时 → 新 adapter」，同步源子类负责合成 envelope。否决。

## Consequences

- 新增上游 = 一个 `BaseBadCaseSyncSource` 子类 + `@BadCaseSyncSourceFactory.register`；服务层、`main.py`、DB 零改动。遍历/租约/重试策略仍在 `BadCaseRootSyncService`，子类不感知遍历。
- `SessionSourceSnapshot` 需扩展可选 `provider`（仅 global 允许）：旧快照 `{"kind":"global"}` 仍合法；带 `provider` 的新快照在回滚到旧代码时被 `extra="forbid"` 拒绝并以 `SESSION_SOURCE_INVALID_RESPONSE` 停车，启动钩子 `reset_deterministic_failures` 负责清快照 re-arm。
- global 线开关语义变为显式：现网若已配端点凭据但未加 `HE_BAD_CASE_SYNC_PROVIDER`，升级后 global 线关闭，部署清单须加一行；装配期对「有凭据无 provider」打 warning。
- payload 产出与现状 `_payload()` 逐字段相同（main → `agent_meta=None`；subagent → `{"parentAgentId": …}`；`runtime_key="claude-code"`），parity 测试已锁定；错误码 `SESSION_QUERY_UNAVAILABLE` / `BAD_CASE_QUERY_UNAVAILABLE` 与 `_NON_RETRYABLE_ERRORS` 不变。
- 目录同步跨方言的 `_upsert_statement` 被显式 `INSERT` + 条件 `UPDATE … WHERE origin = "catalog"` 取代；`PageCounts` 新增 `skipped`，job 结果多一个字段，实现 issue 决定不在状态接口暴露 `skippedBadCases`。
- `create_app` 的 `session_query_source=` / `bad_case_catalog_source=` 注入缝收敛为 `bad_case_sync_source=`，相关测试夹具需改名；新增 `bad_cases.origin` 迁移与回填规则见设计文档 §7.4。
- 工厂层只支持单部署单 provider（与 [Git 推送提供者](../../implemented/architecture/2026-11-21-git-push-provider.md) 一致）；多 provider 并存、`kind="global"` 标签改名均不在本决策内。
