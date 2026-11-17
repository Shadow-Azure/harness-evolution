# Agent Note: 归因报告 V2 与执行清单缓存

Status: implemented

[English](2026-11-17-attribution-report-v2.en.md) | 中文

## Problem

旧 `probe_reports` 只有确定的二元结论、分类和两段文本，缓存身份也无法表达 Skill、模型、上下文或输出 schema；继续在这个边界上接入可插拔 Agent Skill 会复用语义已经变化的旧结果，并把证据不足误写成确定的非目标结论。

## Decision

`probe_reports` 继续作为唯一报告事实源，以可空 JSON 列增量保存 `probe-report/v2` 结构化 payload 和 `attribution-execution/v1` 不可变执行清单。V2 新写入以清单的规范 JSON SHA-256 作为 `cache_key`，清单覆盖 workspace、Badcase、目标 revision、策略、引擎、Skill revision/content hash、模型配置指纹、上下文 snapshot hash 和输出 schema；旧行与未提供清单的写入继续使用七元缓存键。结论扩为 `attributed|non_target|inconclusive`，其中证据不足是 `inconclusive` 且不进入聚类，执行异常仍阻塞 run 而不生成报告。当前规则引擎以 `platform-default@builtin-v1` 和 `model=none` 形成可替换占位，后续 Skill 注册、上下文快照和 Agent 执行器只替换清单输入。

## Alternatives considered

新增第二张 V2 报告表会制造两套报告 ID 与读取优先级，因此否决。原地把所有旧行回填成伪 V2 会声称不存在的 Skill 和上下文证据，因此保留 nullable legacy 兼容。单独增加 `attribution_executions` 审计表被推迟到调度与可观测性迭代：当前 runner 只有同步单次尝试和 run 级阻塞状态，此时建表会先固化尚未设计的重试状态机。

## Consequences

读取 API 可同时返回旧文本与可选 V2 payload/manifest，旧报告不受影响；Skill、模型、上下文或 schema 变化会自然产生缓存 miss。当前上下文哈希只冻结候选 Session、Badcase、命中原因、顺序和两端时间坐标，不保存原始 Trace；完整证据坐标和快照内容由会话归因上下文迭代扩展。数据库多出四个 nullable 列与一个普通索引，MySQL 与 SQLite 共用同一 JSON 契约。
