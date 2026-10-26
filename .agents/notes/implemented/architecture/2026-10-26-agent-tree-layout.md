# Agent Note: Agent 执行流纯布局边界

Status: implemented

[English](2026-10-26-agent-tree-layout.en.md) | 中文

## Problem

Session tree 已由后端返回扁平 Agent、触发事件与显式 bad-case anchor，但原型里的树几何依赖 React Flow、DOM 测量和 JSONL 行差。直接把这些逻辑搬进 Vue 组件会让布局结果依赖浏览器、重复后端口径，并把问题卡渲染与基础图能力耦合。

## Decision

`components/agent-tree/layout.ts` 只消费 `SessionTree`，输出与框架无关的节点、正交通道、分支竖段和 bad-case anchor 描述。布局先复制输入 Agent 与事件，父边修补不会改写调用方数据；重复 Agent 或 main 身份直接 fail-closed，不生成部分重复图。触发链的 `×N` 使用 assistant `messageOffset` 间隔，节点条宽下限由 JSONL 行数按比例计算，文本宽度由注入函数按实际 11px 标签字体提供。触发链过长时节点随链扩展，source handle 与药丸共用最终坐标，不把 handle 留在截断容器外。未知普通父调用只降级到 main 并补合成 agent 事件，不会借用 Workflow。兄弟触发仅在触发点 X 距离不超过 24px 时共用 trunk，超过八个子节点生成 collapse 节点，collapse 竖段也进入问题卡侧向碰撞集合。

`layout.ts` 为 self-skill、self-agent、discovery、fallback 计算锚点，`m4-03` 再把 tree 的最小 bad-case 记录与 `/api/sessions/{sid}/bad-cases` 的五态详情合并为问题卡节点。卡片身份始终是真实 `badCaseId`，位置只取后端 `anchor`，不从 `badCaseAgent` 反推；self-agent 按兄弟分支竖段选择左右侧，skill 卡挂在触发点下方，discovery 卡挂在触发点上方，`eventIndex=-1` 挂在宿主右侧。卡片按可见短 ID 与 reason 的实测文本宽度落在 150–400px，并用同一矩形做跨锚点碰撞处理：同宿主的侧向卡与 skill/discovery 卡稳定向外堆叠，避免不同事件锚点落到同一视觉位置。问题连线使用红色虚线和语义 edge 类型；失效宿主或越界事件保留可见卡片并降级到宿主 fallback，不生成指向不存在节点的孤儿边；宿主仍存在但当前被折叠时则标记为 hidden，不生成左上角浮卡。最小 `AgentTree.vue` 是布局结果的 Vue Flow 薄渲染器，不抓取 Session 数据；开发环境专用的隐藏 `/agent-tree-demo` 默认显示 `demo-nested` 核心树，`?variant=large` 仅用于折叠与 trunk 验证。Session 概览独立读取 summary、tree 与问题详情，三者加载、失败和重试互不阻塞；列表与画布共享一个活动 `badCaseId`，列表选择先展开目标的全部折叠祖先，再等待画布 `setCenter` 后滚动列表；画布卡通过注入回调回到列表并滚动对应行。画布问题卡保持原型的结构性红色，五态颜色只由问题列表与后续详情承载。画布只在拓扑变化时 `fitView`，活动态切换不重新适配；问题定位会取消迟到的 Session 初始滚动重置。Vue Flow 外层 node/edge keyboard focus 关闭，节点内部原生 button 是唯一 Tab 停点；控制按钮提供明确的放大、缩小和适应画布标签，父边使用闭合箭头。Vue Flow 继续留在独立动态 chunk，不进入 `/sessions` 首屏闭包。

`/sessions/:sid?agent=&evidence=` 是当前 Agent 与证据位置的唯一状态源。解析器把 Vue Router 的 path 参数视为已解码，拒绝重复值、控制字符、超长 ID 以及没有 Agent 的 evidence；树响应是 Agent 是否存在和事件下标是否有效的权威。Session 路由移除只属于 error 页的 `case/tab`，error 路由才解析它们供 m4 使用。接受的非规范 query 由 `router.replace` 回写 canonical 形式，后续合法 History 恢复会清除旧的内联提示。evidence 高亮只作用于当前选中的 Agent，同一事件下标不会串亮其他节点。深链目标位于折叠分支时自动展开其祖先，并等目标节点出现后再定位。无效树状态会被清除并显示内联提示，不会回退到其他 Session；自动选中只发生在 `/sessions`，不会用列表首项替换显式但被筛选排除的 Session。节点选择会清除旧 evidence 并写回 canonical URL，1408px 与 390px 都验证刷新恢复、节点可见和无横向溢出，真实 Chrome fixture 还覆盖折叠目标展开。正式的 `/sessions/:sid/errors?case=&tab=` 解析器供 m4 直接使用，但跨 Session 409 不在本地猜测：m4-02 把真实 bad-case 归属响应交给 resolver seam。

## Alternatives considered

- 在 Vue 组件内边测量边布局：结果依赖 DOM 初始化和字体时序，很难稳定单测。
- 沿用 JSONL 行差生成 `×N`：与规范化的 assistant message 口径不一致。
- m3-02 直接渲染问题卡：会让 owner 为 m4 的问题卡视觉与交互提前进入图核心，扩大失败面。
- 用展示序号或“最后一个 Agent”推断卡片身份和位置：会破坏真实 ID 回链与后端锚点语义。
- 依赖 Vue Flow 自定义节点的点击事件冒泡：真实浏览器中不能可靠触发列表联动，因此使用显式注入回调。

## Consequences

布局可输入乱序数组复现相同结果，单元测试不需要浏览器，开发演示路由负责真实画布回归；问题卡另有纯函数测试覆盖四类锚点、堆叠与坏锚点。首屏 bundle 不获得 Vue Flow。真实 Chrome 用四个 fixture Session 覆盖五态、双向定位、活动态唯一、桌面/移动无溢出和 console 清洁。E2E 串行执行，因为每个文件都启动独立的 API、Vite、SQLite 和 Chrome；共享浏览器 launcher 在首次启动失败时清理子进程与 profile 并重试一次。

深链在刷新、历史导航和新窗口导航后恢复同一 Agent/证据位置，且不会序列化私有消息正文。m4 必须先用后端响应验证 case 归属；在此之前，纯 resolver seam 只暴露稳定的 mismatch 契约，不伪造响应。
