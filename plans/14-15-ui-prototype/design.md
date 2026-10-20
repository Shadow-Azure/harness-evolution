# #14/#15 前端原型 UI 设计方案（讨论稿）

> 配套可点击原型：同目录 `index.html`（入口）、`session-explorer.html`（#14）、`timeline.html`（#15）。
> 本稿只用于 UI 讨论，全部数据为打桩样例，不进入产品代码。

## 1. 需求回顾

- **#14 Session 浏览器与家族摘要**：顶层只列 4 个 root session；摘要卡展示 turn / agent / command / failure / skill / finding 聚合数；支持按仓库、时间、状态、问题密度筛选；URL 保存 root session + 选中 agent + 证据位置；空列表 / 未选中 / 加载失败三态明确。
- **#15 Turn 时间线核心渲染**：按 turn 分组；为用户、Agent、推理、工具调用、工具输出、文件变更、错误、token 提供专门卡片；call_id 配对调用与输出；长文本折叠 / 复制 / 看原始载荷；用户消息与最终回复在长轨迹中易定位。

## 2. 调研结论（同类产品的成熟做法）

| 来源 | 值得借鉴的点 |
|---|---|
| [FutureAGI Observe 重设计](https://futureagi.com/blog/redesigning-observe-ui/) | "Triage-first"：列表页直接把错误密度、失败率做成一眼可扫的指示，先分诊再下钻 |
| [LangSmith View traces](https://docs.langchain.com/langsmith/view-traces) | trace 列表 + run tree 双视图；每个节点带状态色、耗时；thread 视图按对话轮次组织长轨迹 |
| Langfuse Sessions | session 是一等单位，列表直接展示聚合指标（turn 数、token、成本），不在列表混进子 trace |
| [claude-code-log](https://pypi.org/project/claude-code-log/) / [claude-log-viewer](https://pypi.org/project/claude-log-viewer/) | JSONL 轨迹 → 聊天式卡片流；thinking / tool_use / tool_result 各自一种卡片，长输出默认折叠 |
| [Superset #5056](https://www.cubic.dev/pr/superset-sh/superset/pull/5056) | 把一个 assistant turn 内的多个步骤折叠成 "step view"，turn 成为天然的折叠边界 |
| [GitLab Session List Redesign](https://gitlab.com/gitlab-org/gitlab/-/work_items/612102) | 会话列表的搜索 + 状态过滤 + 密度信息排版 |

提炼出的通用方法：

1. **列表即分诊**：root session 卡片上直接放聚合数字 + 问题密度条，用户不点进去就能排序出"最值得看的会话"。
2. **turn 是时间线的唯一分组边界**：turn 头吸顶，带序号 / 时刻 / 耗时 / 事件数 / token，长轨迹里永远知道自己在哪一轮。
3. **事件类型 = 卡片类型 = 色彩编码**：每种事件一种卡片、一种主题色，扫读时靠颜色而不是读文字。
4. **默认折叠，按需展开**：推理和长工具输出默认只露摘要，展开后才能复制 / 看原始 JSON。
5. **调用配对要"看得见"**：工具调用与输出用同一条左侧竖线 + 相同 call_id 徽章连成一组，失败输出红色并带退出码。
6. **状态入 URL**：选中项、过滤条件写进 hash/query，刷新可恢复（#14 验收硬要求）。

## 3. 布局方案

三栏壳（M1 阶段右栏留空，后续 #12 问题面板 / #8 执行流图再填）：

```text
┌──────────────┬───────────────────────────────────────────┐
│ Session 浏览器│  主区（两种状态）                           │
│  (#14)       │  A. 家族摘要（未进入时间线时的落地页）        │
│  搜索+筛选    │  B. Turn 时间线（#15，含 agent 切换条）      │
│  4 张家族卡   │                                           │
└──────────────┴───────────────────────────────────────────┘
```

### 3.1 #14 Session 浏览器（见 `session-explorer.html`）

- 每张家族卡：任务标题、启动时刻（20:05 / 17:32 / 08:46 / 12:34 即四类场景的识别符）、仓库、总耗时、后代 agent 数、聚合统计行（turn / 交互次数 / 工具失败 / skill / 问题）、**两条独立密度线**：工具失败密度（红）与问题密度（橙），各自 ÷ 交互次数换算成「每百次交互」（见 §5.2）。
- 筛选：搜索框（标题/仓库）、状态 chips（全部/完成/部分失败/失败）、排序（最新 / 问题最多）。4 个 session 一屏必放得下，筛选主要是验证交互模型。
- 主区家族摘要：顶部只留标题 + 单行紧凑统计条（Turn / Agent / 交互 / 工具失败 / Skill / 问题 / 两条密度值），把纵向空间让给下面的家族成员树 +「打开 Turn 时间线」入口。
- URL 状态演示：`#/session/<id>` 写入 hash，刷新恢复选中（agent 与证据位置同理，原型里先演示 session 一级）。
- 三态演示：右上角可切换「正常 / 空列表 / 加载失败 / 未选中」。

### 3.2 #15 Turn 时间线（见 `timeline.html`）

- 顶部：面包屑（Session 20:05:12 › agent 选择器，下拉内按深度缩进展示家族成员 + 各自状态/问题数）。
- 工具条：事件类型过滤 chips（带计数）、「仅用户消息与最终回复」开关、全部展开/折叠、turn 跳转下拉。
- turn 头吸顶：`Turn 3 · 20:07:41 · 耗时 42s · 8 个事件 · 12.4k tok`。
- 卡片类型与色彩：

| 事件 | 色 | 默认状态 |
|---|---|---|
| 用户消息 | 蓝 | 展开，置顶易定位 |
| Agent 回复 | 绿 | 展开 |
| 推理 | 紫 | 折叠为一行摘要 |
| 工具调用 | 青 | 展开（标题行=工具名+关键参数+状态徽章） |
| 工具输出 | 灰 | 与调用配对；>15 行折叠 + 渐隐遮罩 |
| 文件变更 | 橙 | 展开，diff 统计 |
| 错误 | 红 | 展开，退出码显眼 |
| token 用量 | 灰 chip | 收在 turn 头 |

- call_id 配对：调用卡与输出卡共用一条左侧竖轨，两张卡都带 `call_xxxx` 徽章，点击徽章互相高亮。
- 每张卡右上角：复制 / 查看原始 JSON（打桩弹层）。

## 4. 与验收标准对照

| 验收 | 原型中的对应 |
|---|---|
| 顶层只出现 4 个 root session 并显示后代数 | 列表固定 4 卡，卡片含「后代 agent N」 |
| 区分四类场景 | 启动时刻 + 仓库 + 任务标题 + 密度条四重区分 |
| 一屏内定位 | 搜索 + 状态 + 排序，4 卡一屏 |
| 刷新恢复 | hash 路由演示 |
| 空/未选/失败三态 | 右上角状态切换器 |
| 工具调用与输出不错配 | 竖轨 + call_id 徽章 + 互相高亮 |
| 失败状态与退出码可见 | 红色错误卡 + `exit 1` 徽章 |
| 用户消息/最终回复易定位 | 蓝/绿高对比卡片 + 「仅关键消息」开关 |
| 长输出默认折叠 | 折叠 + 渐隐 + 「展开 N 行」 |
| turn 边界/时间/耗时一致 | 吸顶 turn 头 |

## 5. 我的判断（未经你确认，标出来供推翻）

1. ~~暗色 devtool 风格~~ → **亮色系**（已由你拍板：白底卡片 + 浅灰面板 + 高对比类型色）。
2. 密度**拆成两条线，不合并**（已由你拍板）：工具失败密度 = 工具失败 ÷ 交互次数（红条，3 次/百次满格）；问题密度 = 问题数 ÷ 交互次数（橙条，同样 3 次/百次满格，两条线共用一把尺）。分母用交互次数而非 turn——turn 颗粒度不稳定：1 个复杂 turn 可能含上百次交互，10 个简单 turn 可能只是 10 次模型直回。失败是客观发生的执行信号，问题依赖诊断器质量，两者量纲不同，合并会互相污染。
3. **agent 切换放在时间线顶部下拉**而不是左侧树——树留给 #8 执行流图，避免两处维护层级。
4. **家族摘要作为选中 session 后的落地页**，而不是直接进时间线——先给家族全貌再下钻，符合 ADR 的演示链路「搜索 → 执行流 → …」的第一步。
5. **事件过滤 chips 带计数**，因为长轨迹里用户靠计数判断"这个 session 有没有 MCP / 文件变更"。

## 6. 待讨论

- 整体布局与密度是否符合你的预期？
- 暗色 vs 浅色？
- 家族摘要落地页是否多余（要不要选中直接进时间线）？
- 卡片配色与信息层级。


## 7. 数据源变更：改用 Claude Code 会话（2026-10-19）

原型不再基于 Codex rollout，改为 `~/.claude/projects/<project>/<sessionId>.jsonl` + `<sessionId>/subagents/*.jsonl`。样本取 llm-wiki 的 4 条会话，见 `claude-code.html`。

### 结构差异（原型必须处理）

| 事实 | 处理方式 |
|---|---|
| JSONL 里**没有 turn 字段**，`promptId` 只按 `/clear` 分段（14 次提问仅 3 个 promptId），不能当轮次键 | 轮次由「真实人类提问」派生：`type=user` 且不含 `tool_result`、且不是 skill 注入/中断/命令回显 |
| 工具结果以 `type=user` 记录内联返回，与提问同形 | 按 `tool_use_id` 回填到对应工具卡，不参与轮次切分 |
| 元记录：`queue-operation` / `attachment` / `file-history-snapshot` / `last-prompt` / `mode` | 不进时间线；`attachment` 里的 SessionStart hook（superpowers 注入）只作诊断线索 |
| Skill 注入以「Base directory for this skill…」伪提问出现；中断以「[Request interrupted…]」出现 | 不算轮次，降级为轮内 `metacard`（技能注入 / 中断） |
| 子 agent 转录在独立文件，meta 记录 `agentType` 与 `toolUseId`（对应主会话 Agent 调用） | 家族成员 = 主会话 + 子转录；Agent 工具调用卡直接显示子 agent 类型与描述 |
| assistant 每条记录带 `message.id` 与 usage | 步骤 = `message.id`；token 按步骤聚合到轮次头 |
| 2f5e7ae8 时间跨度 145h（跨 6 天、多次重启） | 时间线展示每步的绝对时刻与轮次内耗时，不做连续时长假设 |

### 派生模型

- **轮次（Round）**：人类提问边界。轮次头 = 提问预览 + 起始时刻 + 步骤数 + 工具数 + 子 agent 数 + token。
- **步骤（Step）**：一次 assistant 响应（`message.id`），含思考 / 正文 / 工具调用 / Agent 调用。
- **轮次长度分布条**：摘要页把各轮步骤数画成段宽成比例的色条（含失败的轮次标红），一眼看出「1 个巨型轮次 + 若干轻量问答」的形状。

### 样本真实统计

| 会话 | 轮次 | 步骤 | 工具 | 失败 | 子 agent | Skill | Token |
|---|---|---|---|---|---|---|---|
| 研究用户数据驱动自进化方法 | 5 | 73 | 39 | 6 | 6 | deep-research、dispatching-parallel-agents | 7.0M |
| AI agent + 视频播放调研 | 12 | 375 | 197 | 4 | 0 | deep-research | 58.4M |
| 学习 DeepSeek Harness | 6 | 117 | 65 | 2 | 4 | — | 11.8M |
| Obsidian 插件机制分析 | 6 | 193 | 97 | 6 | 2 | — | 19.2M |

密度口径沿用 §5.2，分母由「交互次数」改为「步骤数」：失败/百步、问题/百步，两条线共用 3/百步满格。


## 8. 家族树图（替换轮次分布条 / 家族成员 / Skill 列表）

### 实现思路

1. 数据：每个 agent 一条横条，长度 ∝ 该 agent 的 JSONL 行数；Skill / Agent 触发点按 `行号 / 总行数` 定位到条上（例：172 行日志，L27 触发 skill → 条上 15.7% 处）。
2. 布局：主会话在左上；子 agent 节点按触发点的 x 对齐、纵向逐行堆叠（行高 96px），从父条触发点画折线（垂直→水平）连到子节点左侧中点。
3. 视图：固定 470px 高画布，`viewBox 0 0 960 470`，内层 `<g>` 承担缩放/平移；滚轮以光标为中心缩放，拖拽平移，「适应」按钮按内容包围盒等比缩放居中。
4. 交互增强：节点 `<title>` 悬浮提示行号与事件名；「共 N 个节点」提示；图例区分主会话/子 agent/Skill/Subagent。

### 可选技术方案（供后续正式实现）

| 方案 | 适用 | 代价 |
|---|---|---|
| 手写 SVG + transform（本原型采用） | 节点 < ~200、事件标记密集、需完全自定义 | 缩放/命中测试要自己实现 |
| D3（d3-hierarchy + zoom/drag） | 同一棵树要支持动态展开/折叠、动画 | 依赖 d3，样式自己写 |
| AntV G6 / X6 | 需要内置小地图、连边路由、导出 | 包体大，定制节点仍要写 React/Vue 渲染 |
| React Flow | 节点即 React 组件，交互态丰富 | 面板内嵌需 React 运行时，轨迹数据量大时性能要调 |
| Perfetto / Jaeger 式瀑布（行 + 缩进） | 只要"深度缩进 + 时间轴"，不需要连线 | 表达父子触发点不如树直观 |

参考：[Perfetto UI](https://perfetto.dev/docs/visualization/perfetto-ui)（track + slice 的执行流表达）、[AntV G6 自定义节点](http://www.chinadongda.com/j/?weixin_44827945/article/details/125861041)、[Jaeger trace 视图](https://raw.githubusercontent.com/wso2/docs-api-platform/main/en/docs/api-gateway/next/observability/tracing/viewing-traces-in-jaeger.md)、[React Flow](https://github.com/push-forward/react-flow)。
