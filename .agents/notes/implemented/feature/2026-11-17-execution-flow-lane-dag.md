# Agent Note: 执行流默认 lane DAG

Status: implemented

[English](2026-11-17-execution-flow-lane-dag.en.md) | 中文

## Problem

V1 的执行流把整棵 Agent 树画成 Vue Flow 节点图：并发只能靠节点并排暗示，深度靠缩进，`>8` 个子 agent 被折叠成汇总节点，选中 bad case 时还会过滤掉其它分支。V2 原型要求默认视图表达“一次 agent invocation = 一条 lane、bar 左右边界 = 日志行区间、跨 lane 横向重叠 = 并发、`A1/A1.1` 表达深度”，并保留结构树作为切换视图。继续在节点图上叠几何约束，会让布局、选中和性能三处互相牵制。

## Decision

- 新增 `agent-tree/AgentFlow.vue` 作为唯一入口：默认 `lane` 模式，按钮切到 `tree` 模式；两种视图共享 `activeBadCaseId`、`activeAgentId` 与深链，切换不重置选中。
- `agent-tree/lane/laneModel.ts` 是纯函数：树 → lane/bar/marker/并发带/spawn 组。主 lane 固定 `A1`，子 lane 用 `A1.1`、`A1.1.1` 逐级编号；同一父节点按触发行排序，缺失触发行的子 agent 落到父 lane 末端。
- 横轴只用日志行：触发事件占自己的行，两个触发之间的所有行合成 `×N 无触发` bar，因此 main lane 的 bar 连续覆盖 0–100，同一 lane 内不重叠；`messageOffset` 只留给结构树的 message gap，两种 N 不混用。子 lane 的 start 取父触发点，宽度按子 agent 日志行数等比缩放，最长封顶 42%。
- 所有 lane 都渲染，不再有 `>8` 折叠或汇总行；浏览改用固定小窗口视口（`clamp(360px, 48vh, 520px)`）的滚轮缩放、拖拽平移、适应与 1:1 复位。`lane/viewport.ts` 把缩放/平移/fit 做成纯函数，组件只持有 transform。
- 选中 bad case 只加粗定位线并高亮对应 bar，不过滤任何 lane 或分支；BC marker 以 `anchor.agentId + anchor.eventIndex` 解析触发行，落在无触发区间时仍标在该行并说明最近触发点。
- 视图选择用 `localStorage` 的 `he:flow-mode` 记住上次选择；默认仍是 DAG，测试可预置 `tree` 以保持旧结构树回归，不改变生产默认值。
- 结构树整体搬到 `agent-tree/tree/`，继续复用 `layout.ts` 的 `chainOf/buildGraph`；`types.ts` 保留两套视图共享的树类型，并新增 lane 模型类型。因此 Vue Flow 退居切换视图，不再承担默认执行流。

## Alternatives considered

- **继续用 Vue Flow 作为默认执行流**：节点图无法把“并发”表达为横向重叠，且 `>8` 折叠与性能压测会话冲突；拒绝，Vue Flow 只服务结构树。
- **保留 `>8` 折叠并用汇总节点承接**：折叠会丢失 lane 身份，无法定位第 57 个子 agent；拒绝，改为视口缩放/平移。
- **选中 case 时过滤其它分支**：原型明确要求保留全部并发分支，只高亮目标；拒绝过滤，避免把“不存在”误读成“未选中”。
- **用真实时间戳做横轴**：归一化数据没有可靠的 `triggered_at`，伪造 duration 会让 bar 长度失去证据意义；拒绝，先以日志行逻辑序为准，缺失时间戳的 lane 用斜纹 unknown。
- **把每条 bar 都做成真实 DOM 并按虚拟化窗口裁剪**：56 条 lane × 多条 bar 在固定视口内仍可接受，虚拟化会引入定位与 E2E 复杂度；拒绝，先全量渲染，用 transform 缩放。

## Consequences

- 大会话的初始 fit 会把整体缩得很小，读者需要缩放后查看细节；这是“全 lane 展开”的代价。
- 没有真实时间戳时，bar 长度只表示日志行比例，脚注与 tooltip 明确写出“非真实耗时”。
- 子 lane 的位置由父 lane 区间推导，嵌套深度超过三层时路径与缩进仍成立，但可读性依赖缩放。
- 结构树与 lane DAG 各自维护布局，类型与选中状态共享；后续新增执行流能力必须同时考虑两种视图。
- Web 单测覆盖 lane 路径、区间、并发、marker、viewport 与 61 lane 展开；E2E 覆盖默认 DAG、缩放/平移、结构树切换、错误详情选中和 61 lane 压测。
