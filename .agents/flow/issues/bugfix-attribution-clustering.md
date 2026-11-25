# 自进化聚类按归因结论分组，而不是按 bad case 标题

[English](bugfix-attribution-clustering.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-53
milestone: bugfix
depends:
  - bugfix-19
priority: P2
status: done
scope:
  - apps/api/app/service/evolution/**
  - apps/api/app/db/crud/attributions.py
  - apps/api/tests/**
  - apps/web/src/**
  - tests/**
  - plans/**
  - .agents/**
adr:
  - ../../notes/implemented/architecture/2026-11-24-attribution-clustering.md
github:
  number: 587
  url: https://github.com/Shadow-Azure/harness-evolution/issues/587
```

## 背景

生产 run `01M86AXB7180YHS9XY6D67KEG0` 在 20 条 `attributed` 归因上只聚出 3 个簇，成员数 13 / 6 / 1 恰好等于 `attribute_type` 的 `prompt` / `flow` / `error` 分桶。第 1 簇标题是 `[SWE-bench] astropy__astropy-13398 · unresolved`，13 条成员实际跨 `13398` / `13236` / `12907` / `13033` 四个实例、至少 7 种根因机制；第 1 轮 patch 因此同时改传输故障、需求覆盖、回归门禁、增量持久化和完成模板。

根因是分组信号错位：`prepare._build_clusters` 把 bad case 标题交给 `cluster_probes`，而 SWE-bench 适配器生成的标题是固定模板，任意两条 `unresolved` 标题的 Jaccard ≥ 0.429，越过 0.3 阈值即被单链接合并。随后 `cluster.review` 只允许合并草稿、不允许拆分，3 个类目草稿无法再被纠正。归因结论只用于准入和展示，没有参与分组。

## 目标

- 默认分组改为“一条归因结论一个 draft”：`probe_reports.probe_description` 是唯一分组文本，词法层不再按标题合并。
- `cluster.review` 按共同根因合并单 probe draft；title/description 来自归因结论，禁止按实例名、数据集前缀、标题模板或类目合并。
- 降级时按类目生成兜底簇并记 `degraded`，绝不把 N 个单 probe draft 落成 N 个簇。
- 超过 review 输入上限时按类目分批，每批各自完整分区，批次事实记入 `degraded`，不静默退回标题聚类。
- 算法标识升级为 `hybrid-attribution-llm-v1`；旧 run 的 `hybrid-lexical-llm-v1` 读取行为不变。

## 设计依据

- [07 §5.5 分组层](../../../plans/fullstack-design/07-backend-implementation.md)：分组特征与描述生成的现状。
- [07 §5.5.2 聚类三层](../../../plans/fullstack-design/07-backend-implementation.md)：草稿键引用、只合并不拆分、失败策略与成本形态。
- [06 §5.3 probe_clusters](../../../plans/fullstack-design/06-database-design.md)：簇与成员落库契约不变。
- [08 §11 运行详情](../../../plans/fullstack-design/08-frontend-implementation.md)：第 5 步簇卡片与来源 bad case 展示。
- [归因聚类 Agent Note](../../notes/implemented/architecture/2026-11-24-attribution-clustering.md)：本次取舍与备选方案。

## 实现内容

- `AttributionRepository.list_clusterable_probes` 返回 `ClusterableProbe(probe_id, attribute_type, bad_case_id, probe_description)`，避免为分组再查一次。
- `cluster.build_attribution_drafts` 按 `TYPE_ORDER` + `probe_id` 为每条归因生成单 probe draft，摘要取结论并截断到 240 字符；结论为空时生成唯一兜底文本，不把无证据的 probe 合在一起。
- `cluster_llm.build_review_request` 新增 `grouping="attribution"`：摘要来自归因结论，明确“同一处修改可覆盖全部成员”才合并，禁止用实例、模板、类目当共同根因。
- `enhance_clusters` 新增 `grouping`：attribution 失败时 `_fallback_groups` 按类目合并成员，描述为 `{type} 类问题 · {N} 条归因（聚类降级）`；`signature_overlap` 不再从标题重算。
- 超过 `ATTRIBUTION_REVIEW_MAX_DRAFTS` 时按类目分批 review，每批完整分区后合并；批次本身记一条 `degraded`，成功路径仍是一次 review 调用。
- `prepare._build_clusters` 走新路径，`clusters_created` payload 增加 `draftCount`、`draftSummaryMaxChars`、`grouping`；`stages._cluster_item` 的簇标题改为簇描述生成的根因标题，不再取 `cases[0].title`。
- 第 5 步副标题与原型同步改为“按归因根因聚类”。

## 实施步骤

1. 扩展归因仓库读取结论文本。
2. 增加单 probe draft 构造与 attribution review prompt。
3. 改降级兜底、超限分批、算法标识与事件 payload。
4. 改第 5 步簇标题来源与前端文案。
5. 补单测、生产同构 20 条归因回归、文档与 Agent Note。

## 依赖与交付边界

- 依赖：bugfix-19（聚类三层与 `hybrid-lexical-llm-v1` 基线）。
- 交付边界：只改聚类分组层、读取投影、相关契约、测试、前端文案与文档；不改 `probe_clusters` / `probe_cluster_probes` 表结构，不改 patch 生成、评测、推送链路，不引入 embedding。
- 不在本 issue 内：跨类目根因合并、归因 schema 新增 `root_cause_key`、历史 run 重算、真实模型聚类准确率承诺。

## 独立验证

```sh
pnpm test:api -- tests/evolution/test_cluster_attribution_drafts.py
pnpm test:api -- tests/test_clustering_three_layers.py tests/m12-04-clustering-upgrade tests/evolution/test_m10_04_prepare.py
pnpm verify:flow
pnpm verify:docs
```

- 20 条归因 → 20 个单 probe draft，类型分布 13 / 6 / 1；没有两条按相同标题被合并。
- 有效 review 输出每个 draft 键恰好出现一次；同根因可合并、不同根因保持分开；描述不等于任一成员标题。
- review 失败时只落 3 个类目兜底簇，描述带“聚类降级”；`strict` 下不写簇、run 失败。
- 超限输入按类目分批，`degraded` 记录批次事实，簇成员仍完整覆盖全部 probe。
- 旧 `hybrid-lexical-llm-v1` run 的步骤读取不变。

## 验收标准

- `prompt` 类不再整体落成一个簇；13 条同模板标题按根因拆成多个簇，任一簇不同时混入两个实例的不同根因。
- 每个 `attributed` probe 在簇成员里恰好出现一次，`non_target` 不进入簇。
- 第 5 步标题不再是 `[SWE-bench] ...` 原始标题，描述不再出现与成员不符的“同签名记录”。
- 聚类调用仍走 `ClaudeCodeProvider.analyze` + `StructuredSubmission`，不新增 LLM 客户端。
- `clusters_created`、`/steps/clusters` 暴露算法、draft 数与降级原因；`degraded` 时 UI 明确标注。

## 门禁与 CI

- api-static / unit-tests-api / web-tests / docs-flow / flow。
- 新增单测覆盖 20 条归因回归、降级按类目、超限分批、描述不等于成员标题。
- 提交与 PR 标题带 `(#587)`。

## 非目标

- 不引入 embedding/向量库；不新增归因 `root_cause_key`。
- 不重算历史 run；不改表结构。
- 不改变 patch 生成、评测、推送与接纳规则。
