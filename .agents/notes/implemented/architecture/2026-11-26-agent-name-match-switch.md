# Agent Note: 默认 body hash，显式开关放开 agent 名称匹配

Status: implemented

[English](2026-11-26-agent-name-match-switch.en.md) | 中文

> 本决策的部署级开关已被 [成员级名称匹配](2026-11-27-member-name-match-switch.md) 取代；本记录保留当时的取舍。

## Problem

agent 进化对象以 `digest:<sha256(normalize_definition_body(body))>` 作为版本身份；总览版本行按事件 `object_revision`/`definition_hash` 过滤。正文在版本、轨迹快照或运行时注入之间变化时，同名 agent 会被拆成多行：配置 ref 对应的版本行按 hash 过滤后为 0 个 Session，而同一名称的轨迹明明存在。向导与启动本来就按「对象类型 + 名称」关联，总览却按 hash，两个口径不一致。直接改成名称匹配会牺牲同名不同正文的版本精确性，也与「未知不猜名称」的既有决策冲突。

## Decision

- 新增 `HE_AGENT_MATCH_BY_NAME`，布尔值，默认 `false`；启动时读取，修改后需重启 `harness-api`。
- 关闭时行为逐字不变；开启时只对 `object_type=agent` 的 `PotentialMatcher.associated_sessions` 忽略传入的 `observed_revisions`，并且 `TargetOverviewService` 用单个 `defaultRef` 版本行替代事件摘要版本。
- 名称模式行的别名集合覆盖配置 ref、解析 revision、裸 hash 与该对象历史报告的 `object_version`，历史 attributed/nonTarget 报告仍按 case 取最新一条挂在这一行。
- 报告内容身份、`targetRevision`、原文冻结、运行快照、缓存键、第 4 步复用/非该对象统计与后台绑定去重仍按 body hash；skill/knowledge 目标不受影响。
- `TargetContentResolver`/`TargetDefinitions` 不改：启动仍需要 `AGENT.md`，读取失败继续显式返回 `TARGET_CONTENT_UNRESOLVED`；总览名称模式在解析失败时仍按名称关联，但不改写启动链路。
- 历史 digest 版本与报告保留可读；切回关闭即恢复 hash 口径，无迁移回填。

## Alternatives considered

- **全局「名称优先、hash 兜底」**：会让所有对象在所有读取路径放弃版本精确性，并破坏「未知不猜名称」的统一语义；本开关只覆盖 agent 的关联与版本行。
- **总览单独按名称、向导继续按 hash**：两套口径继续分叉，用户仍会在向导与总览看到不同的 Session 集合；共享匹配器一次改动即可对齐。
- **给 target 表加匹配模式列或 UI 开关**：引入契约、迁移与权限面，且部署期开关更适合 `.env`；本 issue 明确不加列、不加表单字段。
- **把名称模式也用于报告缓存与第 4 步统计**：同名不同正文的报告会互相复用，改变报告内容身份与缓存范围；超出本开关边界。
- **迁移历史版本行**：历史 digest 与报告仍可读，回填既无必要也会改写审计事实；开关可随时关闭恢复。

## Consequences

- 开启后同名不同正文的 agent 合并为一行，Session 数与潜在计数会变大；版本精确性由显式 opt-in 换取。
- 总览单行仍尝试解析内容以显示 ref/commit；解析失败时仅缺少 commit，不影响名称关联。启动仍会因同一解析失败报错。
- `targetRevision` 与报告缓存保持 hash，关闭开关即恢复原行为；既有测试断言不需要改写。
- 运维必须在重启 `harness-api` 后才能生效；本开关不进入 OpenAPI、数据库或前端表单。
