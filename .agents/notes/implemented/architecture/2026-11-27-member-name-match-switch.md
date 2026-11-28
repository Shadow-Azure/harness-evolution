# Agent Note: 成员级名称匹配开关取代部署级 env

Status: implemented

[English](2026-11-27-member-name-match-switch.en.md) | 中文

## Problem

skill/agent 版本身份是归一化定义正文的 body hash；同名但正文不同的对象会被拆成多个版本行，配置 ref 行可能没有 Session。上一版用 `HE_AGENT_MATCH_BY_NAME` 在部署级放开 agent 的名称匹配，但它一次切换整台部署的所有 agent，无法让同一配置里的多个成员分别选择，skill 也没有入口；修改还需重启服务。成员编辑框已经逐个维护类型、名称与子目录，开关应跟随成员而不是部署。

## Decision

- `evolution_target_members` 增加 `match_by_name BOOLEAN NOT NULL DEFAULT false`，随成员创建/更新持久化；只在 skill/agent 成员上生效，knowledge 固定 false，合成成员固定 false，历史数据不回填为 true。
- `MatchTarget` 携带 `match_by_name`，`MatchCondition` 始终携带每个成员的目标；`PotentialMatcher.associated_sessions` 只对开启的成员忽略 `observed_revisions`，其他成员保留 body hash 过滤。
- 总览按成员的开关选择单行或现有版本行；名称模式行的别名覆盖配置 ref、解析 revision、裸 body hash 与历史报告 `object_version`，历史 attributed/nonTarget 计数不归零。
- run 的 `evolution_run_targets` 冻结创建时每个成员的 `match_by_name`；launch、prepare 与后台绑定都从成员或快照带入开关，配置后改不重写历史 run。
- 前端在成员行增加「名称匹配」开关，写入契约 `matchByName`；删除 `HE_AGENT_MATCH_BY_NAME`、`Settings.agent_match_by_name` 与 `main.py` 接线，不新增环境变量。
- 报告内容身份、`targetRevision`、原文冻结、缓存键与第 4 步统计仍按 body hash；绑定批次在该字段变化时刷新，历史报告不回写。

## Alternatives considered

- **保留部署级 env 并新增 skill 开关**：仍无法按成员分别选择，一次修改影响整台部署，也要重启；与成员编辑框的粒度冲突。
- **全局「名称优先、hash 兜底」**：对所有对象、所有读取路径放弃版本精确性，破坏「未知不猜名称」的统一语义。
- **只改总览、不改共享匹配器**：向导、启动、总览与后台绑定继续各持一套口径，问题只是从一个视图消失。
- **自动把历史成员回填为 true**：同名不同正文的成员会被静默合并，审计事实被改写；默认关闭、显式 opt-in 才符合风险边界。
- **把名称模式用于报告内容身份与缓存键**：同名不同正文的报告会互相复用，改变报告语义与缓存范围；开关只覆盖关联与版本行。

## Consequences

- 开启成员的 Session 数与潜在计数会变大，版本精确性由显式 opt-in 换取；关闭成员与历史 run 的行为不变。
- 已经设置 `HE_AGENT_MATCH_BY_NAME=true` 的部署升级后全部成员默认关闭，需要按成员重新打开；不提供自动迁移。
- 开关随成员配置持久化，修改后不需要重启 `harness-api`；切换会刷新绑定批次，但历史报告与 `targetRevision` 不重算。
- 每个新增/修改成员的 API 读写都带 `matchByName`，run 卡片也展示冻结值；前端只在 skill/agent 行渲染开关。
