# Agent Note: 运行详情直接消费后端七步状态

Status: implemented

[English](2026-10-27-run-detail-ui.en.md) | 中文

## Problem

运行详情要同时呈现目标输入、workspace、blocked/retry/eval 上下文、七步导航和当前步骤产出。七步 `status/clickable` 的唯一权威已在 m10-04 放到后端；如果详情页根据 `progress.unit` 重算，或逐个探测未到达端点，就会出现第二套状态规则并制造无意义的 `STEP_NOT_READY` 请求。仅复用运行列表或 step 端点也不足：列表没有 workspace 与完整步骤数组，单个 step 响应只描述自己。历史六步 run 还要与新 run 共享同一套界面，因此页面不能保留第二套步骤 schema。

## Decision

- `GET /api/workspaces/{wid}/evolution/runs/{run_id}` 返回 `RunDetail`：复用运行卡片的统计、进度、终态与错误摘要，增加 workspace、blocked/retry/eval 字段、`lastEventSeq` 和七项 `steps`；`steps` 的 key 固定为 `range / sessions / potential / attribution / clusters / iteration / final`。
- 详情服务直接调用与七个 step 端点相同的 `step_states` 游标状态机，并原样输出 `status/clickable`；迭代步只在 active 时生成“第 x/y 轮”detail，前端不按进度推算步骤状态。历史 run 由后端把 V1 probe 投影成同一七步 DTO，前端不区分数据来源。
- 前端详情页只请求 `RunDetail` 和默认可达 step。默认选择第一个 active，否则最后一个 done；URL 的 `?step=` 只在后端标记 clickable 时生效。点击已达节点更新 query 后只请求该 step，pending 节点保持禁用且不触发网络；失败或中断在第一步完成前时，七个节点全部显示“该步骤尚未到达”。
- Step 2 使用服务端 4 条/页、Step 3 使用 5 条/页；翻页只重发当前 step 端点的 `page`，不重算条件。Step 4 一次展示该 step 的全部归因行，并读取服务端 `summary` 的 `potential / reused / fresh / nonTarget`，不从前端行数反推。
- Step 4 的 `category=null` 渲染为“非该对象问题”，`source` 明确标注 cached / fresh；这些行可以在 Step 4 查看，但后端聚类只消费 attributed 候选，所以 non_target 不会出现在 Step 5 的簇里。
- Step 5 按后端给出的 severity 降序展示，默认展开首簇；`?cluster=` 深链只展开并高亮存在的簇，目标不存在时清除参数并提示，不伪造位置。Step 6/7 沿用既有轮次卡与终评卡。
- 目标输入与 workspace 使用同一后端快照：分支、base ref/commit、仓库、子目录、workspace/repo 路径、push/eval 状态和 blocked 错误都来自 run 记录；页面提供明确空态、加载态、失败重试和 `RUN_NOT_FOUND` 无重试态。
- blocked banner 覆盖 patch / push / eval / attribution 四个阶段，展示阶段、脱敏错误、自动重试次数、下一次自动重试时间和人工“重试”按钮；重试受理有短时去抖和自动恢复，不把受理当成功。终评同时展示最终 push 状态与时间，workspace 分支名可点击复制。
- 执行日志以 REST 分页为事实源，`lastEventSeq` 播种 SSE 游标，`run.event` 按 seq 去重合并；带 `stepIndex` 的事件跳转到对应 step，带 `clusterId` 的事件跳转到并高亮簇，错误详情默认折叠且只展示脱敏内容。刷新时重置日志与活动 run，阻止旧 run 事件串入。
- 事件日志、blocked 重试和 step 数据的读取全部沿用现有 API，不新增第二个步骤 schema；cluster_only run 的 iteration/final 由后端 404 隐藏，前端不自行补节点。

## Alternatives considered

- 从前端 `progress.unit` 重算七步状态：与 m10-04 的后端唯一状态源冲突，节点边界、blocked 和 terminal 规则会产生双实现；否。
- 顺序或并行请求七个 step，用 404 判断 pending：会主动请求未到达步骤，违反设计并放大失败路径；否。
- 继续从运行列表拼详情：列表契约没有 workspace、完整 steps、retry/eval 上下文，补齐字段同样会改变 API；否。
- 为 Step 4 再做一套前端分页：契约没有分页字段，前端切页会与服务端行序和统计脱节；本页一次展示服务端返回的归因行，分页交给 API 演进。
- 把 workspace、policy 或 cache 只放在前端本地状态：刷新与深链会丢失后端事实，也无法在 blocked 恢复后复用；否。
- 让 Step 5 前端重新排序簇：后端已持久化 rank/severity，前端重排会与深链、迭代轮次和终评引用不一致；否。

## Consequences

- 运行详情页和视觉/E2E 只依赖一个详情壳加一个 step 请求，刷新、深链、翻页和未到达禁用共享同一契约。
- `GET /runs/{rid}` 与 step 端点共同依赖 `step_states`；未来 cursor 规则变更必须同时覆盖详情和七步测试。
- blocked stage 使用共享契约闭集（patch/push/eval/attribution），新增状态时必须同步 API Literal、生成契约、前端状态测试和原型文案。
- 事件日志与 step 的联动依赖 `stepIndex` 与 `clusterId` 两个可选坐标；新增事件类型时不改页面 schema，只复用现有跳转规则。
- V2 run 和 legacy run 的 E2E fixture 都写入真实七步 DTO 所需的候选、probe、簇、轮次与事件行；E2E 覆盖会话/潜在翻页、cached/fresh/non_target、簇严重度顺序与首簇展开、blocked attribution 重试事实、未到达 step 不请求，以及事件到 step/cluster/error 的联动。
