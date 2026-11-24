# Agent Note: 七步投影的来源 bad case 标题取短标题

Status: implemented

[English](2026-11-24-iteration-source-case-title-projection.en.md) | 中文

## Problem

运行详情第 6 步「迭代优化」与第 5 步「聚类与严重度」的来源 bad case 表把归因摘要当标题渲染：`StepClusterCase.title` 由 `_cluster_cases()` 填充，V2 分支取 `attribution_by_case[bad_case_id].probe_description`，legacy 分支取 `probe_row.probe_description`。生产单个 run 20 条，单条 422–1541 字符、平均 795，每行被撑成多段长文，object_name、类型、触发点与上报时间被挤到右侧，无法逐行核对本轮覆盖的 case。`bad_cases.title` 按设计是上报必填的短标题（生产样例 47 字符），`reason` 才是描述正文；两级文本在数据里本来就分得开，是七步投影取错了字段（GitHub #570）。同类「数据通路已有短字段但投影丢字段」的修复先例见 [2026-11-20-run-detail-session-short-title.md](2026-11-20-run-detail-session-short-title.md)。

## Decision

- 批量读标题：`BadCaseRepository.titles_by_ids()` 用一条 `bad_case_id IN (...)` 的只读 SELECT 返回 case-id → 短标题映射，`@read_only_guard("bad_cases")` 沿用外部表错误边界；空入参直接返回空字典。
- 在 facts 层装配：`_facts()` 按候选是否存在选择本次 run 的 case 来源（有 candidate 用 `candidates[].bad_case_id`，否则用 `probes[].bad_case_id`），保序去重后只调用一次 `titles_by_ids()`，结果放进 `_RunFacts.case_titles`。投影函数 `_cluster_cases()` 的两个分支只做字典查找，不再按行查询。
- 两条投影统一取短标题：V2 分支为 `facts.case_titles.get(candidate.bad_case_id) or candidate.bad_case_id`，legacy 分支为 `facts.case_titles.get(row.bad_case_id) or row.bad_case_id`。标题缺失是容错分支，回退到可稳定识别的 `bad_case_id`，不再回落到 `probe_description`。
- 第 4 步边界不变：`StepAttributionRow.description` 仍取归因摘要 `probe_description`；`_v2_attribution_rows()` 与 `_legacy_attribution_rows()` 未改，长文只在该列出现。
- 契约与前端零改动：`StepClusterCase` 字段不变，无 OpenAPI/生成类型或 `apps/web` 改动；历史 run 不需要重新准备，读取时实时补标题。

## Alternatives considered

- **对每个 case 调用 `get_case()` 逐行查询**：拒绝。一次 run 几十条 case，逐行查询把装配变成 N 次数据库往返，而七步投影每次请求都会重建 facts。
- **在 `StepClusterCase` 上新增 `detail` 或摘要字段**：拒绝。这是契约与前端改动，超出本 issue 的交付边界；标题列的问题是取错字段，不是缺字段。
- **前端截断 `probe_description` 或使用 `line-clamp`**：拒绝。issue 明确列为非目标；截断仍在标题列显示归因正文，还把展示规则复制到客户端。
- **缺失标题时回退 `probe_description`**：拒绝。这正是本 issue 要消除的混用；`bad_case_id` 虽不可读但语义正确、可对照排查，不会让长文重新进入标题列。
- **在 `_RunFacts` 之外做进程级标题缓存**：拒绝。标题属于外部表、随时可更新，缓存会引入失效问题；单次请求一次批量读已经足够便宜。

## Consequences

- 第 5/6 步来源表标题列恢复为来源 bad case 的短标题，第 4 步「问题现象/描述」列继续显示完整归因摘要；两级文本在投影里各归其位。
- `_RunFacts` 增加 `case_titles` 这一必填依赖，`EvolutionStageService` 的构造签名多一个 `BadCaseRepository`；生产装配在 `main.py` 复用同一个仓库实例，`tests/evolution` 与占位评测测试同步补依赖。
- 每次七步请求多一条 `IN` 查询；候选与 probe 两条路径都只查一次，不随 case 数量增长。
- 历史 run 无需重新准备；`bad_cases.title` 本身异常过长的存量数据不在本 issue 的处理范围。
