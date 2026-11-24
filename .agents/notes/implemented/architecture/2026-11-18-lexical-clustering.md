# Agent Note: 确定性词法聚类替代占位分半

Status: implemented

[English](2026-11-18-lexical-clustering.en.md) | 中文

## Problem

自进化第五步的 V1 聚类按类型排序后把探针对半切开，簇成员与问题的语义无关，只够让七步流程跑通。M12 要求把这一步换成真实聚类，同时保持 `probe_clusters` / `probe_cluster_probes`、API 字段和评分口径不变，并保证空输入、单元素、重复输入和大输入都有确定行为。

直接对 `probe_reports.probe_description` 做文本相似度不可行：`rule-v1` 的结论是模板句（“对象自身上报：…；未发现错误证据，按 prompt 归类”），两个不同问题的模板词重叠就能到 0.70，模板会淹没案例差异。

## Decision

- 聚类特征取 bad case 标题 `bad_cases.title`：它是上报方对问题的摘要，比模板化的归因 reason 更能区分案例；标题随候选从外部问题表只读加载。
- 每个 `attribute_type` 独立聚类。文本转成 ASCII 词元与 CJK 字符二元组集合，两个集合的 Jaccard ≥ `0.3` 视为相似；相似关系取单链接连通分量，同簇成员不再按数量对半切。
- 空文本不参与合并，单独成簇；重复 `probe_id` 先按 `(attribute_type, text)` 去重。簇与成员按 `probe_id` 排序，空输入返回空结果，因此同输入同输出且与数据库行序无关。
- 簇描述为 `"{type} 类问题 · {簇内最小 probe_id 的标题}"`，标题空白归一化并截断到 120 字符；没有标题时用成员条数兜底。
- 算法身份 `CLUSTER_ALGORITHM = "lexical-jaccard-v1"`、阈值和簇结果 hash 写入 `clusters_created` 事件 payload，作为 run 的复现参数。
- 写入路径、表、关联和评分公式不变：仍写 `probe_clusters` / `probe_cluster_probes`，`confidence`、`impact`、`severity`、`rank` 继续按 [06 §5.3](../../../../plans/fullstack-design/06-database-design.md) 计算。

## Alternatives considered

- **继续按数量分半**：实现最简单，但簇与语义无关，无法兑现 M12 的算法升级；拒绝。
- **对归因 reason 做 TF-IDF/余弦**：规则引擎 reason 的模板词高度共享，实测两个不同问题相似度约 0.70；换用标题后模板噪声消失。
- **固定 k 的 k-means**：需要先验簇数；把不相关问题强行合并会改变 severity/轮次口径，也超出本 issue 的可独立验收边界。
- **向量模型或外部聚类服务**：会引入新依赖、外部资源和部署配置，本 issue 要求无 schema 变更、无新增资源即可验收；留给后续真实服务替换。
- **保留旧 `simple_cluster` 作对照**：历史 run 的簇已落库，不需要重新计算；生产保留死代码会让两个算法口径长期并存。对照行为改由测试中的“升级前后”用例表达。

## Consequences

- 簇数不再被限制在每类两个；一轮对应一个簇，因此问题更分散时轮次会变多。这是更细粒度聚类换来的成本，若要限制轮次需另立 issue 设计调度策略。
- 词法相似不等于语义等价，标题语言与长度会影响结果；本 issue 不承诺诊断准确性，算法版本与阈值随 run 事件落库，便于后续复现和替换。
- `m5-01` 的占位聚类测试随算法删除；`tests/m12-04-clustering-upgrade` 覆盖相似/不相似标题、阈值边界、空输入、单元素、重复输入、空白标题、大输入与 prepare 落库。
- 生产默认分组已改为按归因结论（[2026-11-24 归因聚类](2026-11-24-attribution-clustering.md)）；本 Note 的标题词法仅保留给无 agent 的离线/测试路径与旧 `hybrid-lexical-llm-v1` run 回放。
