# Agent Note: 运行详情直接消费后端六步状态

Status: implemented

[English](2026-10-27-run-detail-ui.en.md) | 中文

## Problem

运行详情要同时呈现目标输入、workspace、blocked/retry/eval 上下文、六步导航和当前步骤产出。六步 `status/clickable` 的唯一权威已在 m5-06 放到后端；如果详情页根据 `progress.unit` 重算，或逐个探测未到达端点，就会出现第二套状态规则并制造无意义的 `STEP_NOT_READY` 请求。仅复用运行列表或六个 step 端点也不足：列表没有 workspace 与完整步骤数组，单个 step 响应只描述自己。

## Decision

- `GET /api/evolution/runs/{run_id}` 返回 `RunDetail`：复用运行卡片的统计、进度、终态与错误摘要，增加 workspace、blocked/retry/eval 字段、`lastEventSeq` 和六项 `steps`。
- 详情服务直接调用与六个 step 端点相同的 `step_states` 游标状态机，并原样输出 `status/clickable`；迭代步只在 active 时生成“第 x/y 轮”detail，前端不按进度推算步骤状态。
- 前端详情页首次只请求 `RunDetail` 和默认可达 step。默认选择第一个 active，否则最后一个 done；URL 的 `?step=` 只在后端标记 clickable 时生效。点击已达节点更新 query 后只请求该 step，pending 节点保持禁用且不触发网络。
- 当 run 在第一步完成前失败或中断时，六个节点全部不可读；页面直接显示“该步骤尚未到达 / 运行在第 1 步完成前已终止”，不把禁用查询误判成永久加载。
- 目标输入与 workspace 使用同一后端快照：分支、base ref/commit、仓库、子目录、workspace/repo 路径、push/eval 状态和 blocked 错误都来自 run 记录；页面提供明确空态、加载态、失败重试和 `RUN_NOT_FOUND` 无重试态。
- 六步组件直接渲染 05 §3.6 的结构化 payload：筛选行按 probe ID 合并重复输入，聚类与迭代卡展开后复用同一张六列来源问题表，报告 ID 指向归因 tab、来源问题 ID 指向问题描述 tab；归因分析用禁用 raw HTML 的 Markdown 渲染，严重程度按后端顺序展示。
- 迭代卡以 round status 与 push/eval failure substatus 的闭集映射生成 patch、推送、评测、决策、接纳、拒绝和失败文案，并用 run-level blocked stage 标明 patch/push/eval 的阻塞位置；round status 不包含 blocked，deciding 不算终态。评测结论由 accepted 决定，不根据分数高低宣称 candidate 已提升。终评同时展示最终 push 状态与时间，workspace 分支名可点击复制。
- `lastEventSeq` 当前为 0，事件表与分页/SSE 的消费由 m5-08 接管；blocked 的自动重试动作由 m5-11 接管，详情页只呈现当前恢复上下文，不提供人工 advance。

## Alternatives considered

- 从前端 `progress.unit` 重算六步状态：与 m5-06 的后端唯一状态源冲突，节点边界和 terminal/blocked 规则会产生双实现；否。
- 顺序或并行请求六个 step，用 404 判断 pending：会主动请求未到达步骤，违反设计并放大失败路径；否。
- 继续从运行列表拼详情：列表契约没有 workspace、完整 steps、retry/eval 上下文，补齐字段同样会改变 API；否。
- 把 workspace 只放在前端本地状态：刷新与深链会丢失后端事实，也无法在 blocked 恢复后复用；否。

## Consequences

- 运行详情页和视觉/E2E 只依赖一个详情壳加一个 step 请求，刷新、深链和未到达禁用共享同一契约。
- `GET /runs/{rid}` 与 step 端点共同依赖 `step_states`；未来 cursor 规则变更必须同时覆盖详情和六步测试。
- Round/push/eval 与 blocked stage 使用共享契约闭集：blocked stage 只允许 patch/push/eval，round status 只允许执行态和终态；新增状态时必须同步 API Literal、生成契约、前端状态测试和原型文案。
- m5-08 可在同一 detail 契约回填真实 `lastEventSeq`，m5-11 可在 blocked banner 接恢复动作，无需前端重算步骤状态。
- fixture 为每个 cluster 写入 session、bad case、probe 与关联行，并让 run/round/workspace 的 push/eval 状态相互一致；completed、running/evaluating、blocked、无效 cluster 深链和 390px 布局都由 E2E/组件测试覆盖。
