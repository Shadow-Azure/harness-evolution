# Agent Note: agent 进化对象的可选名称匹配模式

Status: implemented

[English](2026-11-26-agent-name-matching-mode.en.md) | 中文

## Problem

agent 进化对象的版本身份是 `AGENT.md` 归一化 body hash：目标解析器按选中 ref 读文件得到 `targetRevision=digest:<sha256>`，总览目标分析的版本行再用事件 `object_revision`/`definition_hash` 过滤 Session。agent 事件的 `object_revision` 是 `agentType + builtin 标记 + body hash` 的组合摘要，与目标解析出的纯 body hash 不是同一个值；同一 agent 名称的正文又常在不同版本、轨迹快照或运行时注入之间变化。结果是同名 agent 在总览里被拆成多行摘要，配置 ref 对应的版本行按 hash 过滤后可能为 0 个 Session，而向导、启动与后台绑定早已按「对象类型 + 名称出现」关联，两个读取口径不一致。

完全按名称匹配会牺牲「同名不同正文」的版本精确性，不能作为默认行为；需要一个显式、可配置、默认关闭的例外。

## Decision

- 新增 `HE_AGENT_MATCH_BY_NAME`（`Settings.agent_match_by_name`，布尔，默认 `false`，启动时读取，改后重启 `harness-api`）。
- 开启后只对 `object_type=agent` 生效：`PotentialMatcher.associated_sessions` 忽略 `observed_revisions`；`TargetOverviewService` 为 agent 目标构造单个以 `defaultRef` 为键和显示的版本，按名称关联窗口内所有含该 agent 的 Session，并为该行构造历史报告别名（配置 ref、解析 revision、裸 hash 与历史报告 `object_version`），使 `_newest_link_by_case` 仍能选中既有报告，attributed/nonTarget 计数不因版本折叠归零。
- 报告内容身份、`targetRevision`、原文冻结、运行快照、缓存键、第 4 步 `reused/fresh`/`nonTargetKnown`、启动 latest-reports 门与 `BindingWorker` 完成去重仍按 body hash；名称匹配只改关联与版本行这一层。
- skill/知识库、事件采集、数据库结构与 OpenAPI 契约不变；历史 digest 版本与报告保留可读，不做迁移或回填；`AGENT.md` 仍是启动与归因的必需内容，读取失败继续显式报错。

## Alternatives considered

- **始终按名称匹配 agent**：会让同名不同正文的 Session 默认混在一起，失去当前 hash 身份的版本证据；默认关闭、显式 opt-in 才不改变现有部署语义。
- **把 agent 的 `targetRevision`、报告缓存键或原文冻结改成名称**：同名不同正文的报告会互相复用，内容身份与 patch 基线不再可追溯；本决策只改关联和版本行，报告范围仍按 body hash。
- **全局「名称优先、hash 兜底」自动回退**：命中规则依赖数据是否恰好缺失，无法解释同一空间内不同 case 的行为；显式开关更可审计。
- **在总览里保留 digest 版本并逐行按名称关联**：同一 Session 会在多个版本行重复计数；单版本行才能让名称匹配的统计稳定。
- **加 UI 开关或表单字段**：本需求是部署级 `.env` 行为，UI 开关会增加按用户差异的语义；不采用。

## Consequences

- 开关开启时，同一 agent 名称的不同正文版本在总览聚合为一行，版本精确性让位于名称关联；历史报告靠别名保留，新的 attributed/nonTarget 计数可能因同名 Session 扩大而增加。
- 报告缓存与 latest-reports 启动门仍按 body hash，`AGENT.md` 内容变化会带来新的报告 scope；这是有意的内容身份边界。
- 开关读一次进程配置，改值需要重启 `harness-api`；默认关闭时行为逐字不变。
- 没有数据库迁移；历史 digest 版本、报告和运行快照保持原样。若未来产品要名称成为唯一身份，需要另开设计，处理报告复用与迁移。
