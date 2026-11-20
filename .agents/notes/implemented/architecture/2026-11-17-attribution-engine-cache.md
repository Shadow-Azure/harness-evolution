# Agent Note: 对象级归因引擎、缓存与候选写入

Status: implemented

[English](2026-11-17-attribution-engine-cache.en.md) | 中文

## Problem

潜在 case 只是「可能与该对象有关」；自进化还需要按对象·revision 给出可复用的归因结论，并区分 `attributed`、`non_target` 与尚未分析。V1 把归因压成 case 的 1:1 状态，没有缓存键、复用计数、知识证据，也没有「运行详情为什么这样判」的落库位置。若引擎直接读写数据库，缓存命中、并发 upsert 和失败恢复会与规则逻辑纠缠；若每次重跑都重算全部候选，`blocked(attribution)` 后的恢复会重复消耗引擎并覆盖已完成结论。

## Decision

- 引擎是纯函数：`AttributionEngine` 只接收 `AttributionInput`（坏例标题/描述/元数据、命中原因、两个触发点、knowledge 文档证据、对象 revision），返回 `AttributionResult`。首版 `rule-v1` 使用确定性模板：自身上报且存在错误证据 → `attributed/error/0.8`，自身上报无错误证据 → `attributed/prompt/0.8`，`after_object` 且 discovery → `attributed/error/0.6`，证据不足或顺序不可比 → `inconclusive/None/0.0`。
- 注册表只登记显式 key：`resolve_attribution_engine` 对未注册 key 抛 `ConfigError`；`create_app` 在启动时校验 `HE_ATTRIBUTION_ENGINE`，未知引擎直接启动失败。缓存键与引擎 key 绑定，换真实模型只需新增 Engine 子类并注册新 key。
- V2 缓存键是不可变执行清单的规范 JSON SHA-256，除原七元身份外还覆盖 Skill、模型、上下文 snapshot 与输出 schema；没有清单的旧写入继续使用七元键。`object_version` 分量使用解析后的 `targetRevision`，`probe_reports.object_version` 长 96，使 `digest:<sha256>`（71 字符）与 `tag:` / `provider:` 形式无需截断。
- `AttributionRunner` 负责缓存与写入：命中且 `cache_enabled` 时复用 `probe_id`、`reused_count` 每 run 只加一次、候选 `is_cached=true`；`cache_enabled=false` 时跳过读并覆盖同键行、更新 `created_run_id`，不清零历史复用计数；同键写入继续走 SQLite/MySQL 方言原子 upsert。
- 新 repository 方法 `write_probe_and_link` 与 `reuse_probe_and_link` 在**一个事务**内完成 probe upsert、`bad_case_analysis` 关联和候选 `probe_id/is_cached` 指针；候选行缺失时整体回滚，避免孤立 probe。runner 用 `linked_probe_ids` 跳过已完成候选，因此失败重跑只补未完成项。
- `non_target` 的 `attribute_type` 为 NULL，probe 与关联保留供错误详情读取；`list_clusterable_probe_ids` 只返回 `included=true` 且 `conclusion='attributed'` 的 probe，聚类输入不会混入 non-target 或被策略排除的行。
- knowledge 证据按 case 的根 Session 批量读取（`agent_events.kind='knowledge'` 的 document/path/revision/retrieval kind），进入 `rule-v1` 的 reasoning；无错误字段但存在知识文档证据时，自身上报按 prompt 归类。
- 新增 `evolution_runs.potential_policy / cache_enabled / attribution_engine` 快照列（旧 run 默认 `NULL / false / legacy-probe-import`）。`blocked_stage` 的封闭集合加入 `attribution`，事件与 jobs 映射到 `prepare`；`/retry` 对 attribution 没有迭代现场可恢复，沿用「无 rounds → 重新入队 `evolution_prepare`」路径，由 prepare 重入时跳过已关联候选。

## Alternatives considered

- **引擎直接查库/写库**：命中与并发逻辑会渗透进规则分支，换模型时难以保证缓存语义；拒绝，引擎保持纯函数。
- **把 71 字符 digest 截断或哈希成 64 字符写入**：会丢失 revision identity，读模型与缓存键无法解释同一对象版本；拒绝，扩列到 96。
- **先查 `cache_key` 再插入**：并发下会撞唯一键或产生重复 probe；拒绝，继续用方言原子 upsert。
- **probe、关联、候选分三个事务写**：中途失败会留下无候选指针的 probe，重跑无法判断哪些已完成；拒绝，单事务写入并在候选缺失时整体回滚。
- **缓存关闭时同时重置 `reused_count`**：复用计数是历史审计事实，不是当前结论的一部分；拒绝，只刷新结论字段与 `created_run_id`。
- **重跑时重算所有候选**：会重复调用引擎并覆盖已完成结论，违背「只补未完成项」；拒绝，用候选 `probe_id` 作为完成标记。
- **把 non_target 也交给聚类**：没有 `attribute_type` 的成员会污染簇与 severity；拒绝，repository 只投影 attributed probe。

## Consequences

- 缓存键取决于完整执行清单；同一对象的不同 revision、引擎、Skill、模型、上下文或 schema 各自一行，历史结论可保留但不会被新执行配置命中。
- `rule-v1` 是占位规则，reason/reasoning 是模板文案；它不声称最终模型质量，也不执行真实 LLM 排名。
- 归因事件按批记录（每 20 条一条 `attribution_created/reused`）留给 m10-04 的 prepare 模板；本切片只返回 `processed/created/reused/non_target/skipped` 供其汇总。
- `blocked(attribution)` 的 `/retry` 目前只验证「恢复状态 + 重新入队 prepare」；prepare 内的归因重入与状态机游标由 m10-04 接管。
- 历史 V1 run 的 `attribution_engine` 保持 `legacy-probe-import`，不会被 `rule-v1` runner 误用；旧 probe 若无法计算七元组仍保持 `cache_key=NULL`，不会伪造缓存身份。
