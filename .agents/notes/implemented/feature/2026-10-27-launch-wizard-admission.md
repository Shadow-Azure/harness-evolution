# Agent Note: 启动向导的同步校验与 202 受理语义

Status: implemented

[English](2026-10-27-launch-wizard-admission.en.md) | 中文

## Problem

m5-05 启动向导需要在不引入第二套设计的前提下落地 05 §4.9/§4.10 与 07 §5.3：probe 预览要给向导第二步提供真实命中统计，启动要先把同步校验失败（对象未配置、零命中、窗口倒挂）挡在写库之前，而真正的筛选与聚类又必须异步执行。边界在于：`POST /runs` 的 202 只是"已受理准备"，prepare 的执行编排属于 m5-06 的六步流程。

## Decision

- 命中口径统一为"该对象 pair 的 `analyzed_issue` 报告"：`badCases` 按 `bad_cases.object_*` 匹配计数，`probes`/`items` 只来自 analysis 关联的 probe；未分析报告只进 `unanalyzed` 计数并提示等待外部归因，零命中统一 `409 NO_PROBES_MATCHED`。
- `POST /api/evolution/probes/query`、`POST /api/evolution/runs`、`POST /api/evolution/cluster-previews` 共用 `ProbeQueryRequest` 与同一套校验；启动时目标快照（repo_url/sub_dir/default_ref）、窗口、模型、engine_key（默认 = mode）与 eval 配置在建行时全部落库，保证启动参数可追溯。
- 创建成功只落一行 `status=preparing` 的 `evolution_runs` 并入队 `evolution_prepare`；本切片不注册 prepare 执行 handler，run 停在 preparing/聚类结果留待 m5-06，cluster_only 由此天然只可能出现 preparing 状态。
- 前端向导按原型两步实现：只列出已配置且启用的对象、下一步执行预览、第二步渲染统计/分布条/probe 表并提供「仅聚类」与「启动自进化」两个出口；启动后分别跳 `/evolution/runs/:rid` 与 `/evolution/cluster/:rid` 的准备态落地页，完整详情页留给 m5-07。

## Alternatives considered

- 预览走 GET 加 query string：条件含模型数组且与启动 body 复用，POST body 更贴合 05 §4.9 的定义；否。
- 在本切片实现 cluster_only 的 prepare handler（筛选→simple_cluster→落簇→终态）：需要补 run 状态迁移与步骤 API，属于 m5-06 的交付边界；否。
- 向导启动后原地轮询直到聚类完成：202 语义明确"不要等"，详情/预览页轮询是 m5-07/08 §11 的职责；否。

## Consequences

- `NO_PROBES_MATCHED` / `TARGET_NOT_CONFIGURED` 成为前后端共享的错误码，向导第一步必须把 409 展示为"调整条件"而不是失败页。
- 在 prepare handler 接线前，任何 run 都不会离开 preparing；运行列表会持续显示"准备中"，这是预期占位而非缺陷。
- 落地页以运行列表接口取单条数据，`GET /runs/{rid}` 独立端点与 SSE 订阅在 m5-07/05 §4.10 收口时需要替换这一实现。
