# Agent Note: 自进化聚类改读归因结论

Status: implemented

[English](2026-11-24-attribution-clustering.en.md) | 中文

## Problem

2026-11-24 的生产 run `01M86AXB7180YHS9XY6D67KEG0` 有 20 条 `attributed` 归因，第 5 步却只产出 3 个簇，成员数 13 / 6 / 1 与 `prompt` / `flow` / `error` 类目一一对应。第 1 簇标题是 `[SWE-bench] astropy__astropy-13398 · unresolved`，13 条成员实际跨四个实例、至少七种机制；第 1 轮 patch 因此同时改传输故障、需求覆盖、回归门禁、增量持久化和完成模板。

旧的词法分组取 `bad_cases.title`。这个前提来自 m12-04：当时 `rule-v1` 的 `probe_description` 是模板句，两个不同问题的模板词重叠约 0.70，标题反而更能区分案例。V2 归因已经是真实模型结论，逐案不同，但分组仍停在标题假设上。SWE-bench 适配器生成的标题是固定模板，实例号只占一个 token，任意两条 `unresolved` 标题的 Jaccard ≥ 0.429，必然越过 0.3 阈值并被单链接合并。`cluster.review` 只能合并、不能拆分，3 个类目草稿无法再纠正。归因结论只参与“能否进簇”和类目分桶，从未决定“和谁一簇”。

## Decision

- 分组信号改为归因结论：每条 `attributed` probe 用自己的 `probe_reports.probe_description` 生成一个单 probe draft，词法层不再按标题合并；摘要截断到 240 字符。
- `cluster.review` 保持既有任务键和 `{"from": [...]}` 输出契约，语义从“合并词法草稿”变成“按共同根因合并单 probe draft”。prompt 明确禁止用实例名、数据集前缀、标题模板或类目当共同根因；同根因跨实例可以合并，不同根因即使标题相同也必须分开。
- 降级时按类目生成兜底簇，描述为 `{type} 类问题 · {N} 条归因（聚类降级）`，不把 N 个单 probe draft 落成 N 个簇，也不伪造根因描述。
- review 输入超过 `ATTRIBUTION_REVIEW_MAX_DRAFTS = 200` 时按类目分批，每批各自完整分区；批次事实写一条 `degraded`，成功路径仍是一次 review 调用。
- 算法标识升级为 `hybrid-attribution-llm-v1`；`hybrid-lexical-llm-v1` 仅用于读取旧 run 与无 agent 的 legacy 路径。
- 第 5 步簇标题改由簇描述生成，不再取第一个成员的 bad case 标题。表结构与评分链路不变。
- `signature_overlap` 在归因分组下不再从标题重算，保留为 0 的统计占位；标题不再是分组或紧密度信号。

## Alternatives considered

- **只调 `SIMILARITY_THRESHOLD`**：标题 Jaccard 最小 0.429、归因全文最大 0.178；调阈值只能把“全合并”换成“全单例草稿”，不能得到根因分区。
- **只换字段、保留词法合并**：归因全文的 pairwise Jaccard 最大 0.178，阈值降到 0.12 会把不相关机制链在一起；语义合并必须交给 review 层。
- **允许 review 拆分草稿**：会破坏“成员由代码持有、输出 O(K)”的守恒，也让输出与输入键不再一一对应；保持 merge-only 更可校验。
- **用类目或实例直接分组**：类目是 5 值粗分类，实例是数据集身份，都不是可操作根因；这正是本 run 的错误结果。
- **引入 embedding/向量库**：能改善召回，但需要新资源与部署配置，也仍不能替代“同一处修改可覆盖”的根因判断；留给后续可选升级。
- **让 review 失败后落 N 个单例簇**：会把每个归因变成一轮迭代，成本和噪声不可接受；按类目兜底并显式标记降级更诚实。

## Consequences

- `cluster.review` 的输入从 O(K) 变为 O(N)，N=20 时约 6k tokens，仍是一次调用；N 的上限与分批策略保证 prompt 有界，但跨批次的根因无法合并。
- 聚类质量取决于归因结论与 review 模型；本决策只保证“分组信号来自归因结论”且分区可校验，不承诺准确率。
- 旧 run 的 `hybrid-lexical-llm-v1` 步骤读取与历史 hash 不变；新 run 的算法标识、draft 数与截断策略进入 `clusters_created`，便于回放。
- 无 agent 的 legacy 词法路径保留给测试与离线调用，生产装配始终绑定 provider，因此生产默认路径是归因分组。
- 前端标题不再复制第一个成员的 case 标题；描述降级文案显式标注“聚类降级”，避免把类目桶误读成根因簇。
