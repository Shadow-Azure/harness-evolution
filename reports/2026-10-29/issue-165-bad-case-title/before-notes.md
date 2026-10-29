# issue #165 修复前核对记录

日期：2026-10-29。分支 `feat/165-bad-case-title`（基线 `main@f37010d`）。

## 原型基准（harness-evolution.html）

深链：`plans/14-15-ui-prototype/harness-evolution.html?page=session&view=errors&sid=050b81ba-…&issue=I-050b-01&dtab=desc`

- 截图：`screenshots/01-prototype-error-detail.png`（整页）、`screenshots/02-prototype-ed-panel.png`（问题描述面板特写）。
- 标题行（`.ed-head` 内 `.ed-title`）：`重复加载`（短标题）。
- 正文块（`.ed-detail`）：`同一份检索模板在 3 个步骤中重复加载，未命中缓存，额外产生 2 次工具调用。`（完整描述）。
- 事实 chips（`.fi-facts`）：`调用次数 3`、`缓存命中 0 / 3`、`额外耗时 ≈ 12s`。
- 关联行（`.ed-meta`）：`关联：skill · deep-research · 会话：研究'用户数据驱动自进化'提到的所有方法`。
- 原型 CSS：`.ed-title { font-size: 15px; font-weight: 650 }`、`.ed-detail { margin-top: 9px; font-size: 12.5px; line-height: 1.7; color: var(--text-dim) }`。
- 原型问题列表卡（`.err-card-title`）与执行流问题卡（`.rf-finding` 文本）同样只展示短标题。

## 修复前的当前 UI

截图来源：`collect-before.mjs` 在 `git archive f37010d`（本次变更前的提交）出来的临时快照上跑真实前后端；只改临时库的一条 `bad_case_description` 为真实长描述，不改仓库文件。该次采集同时产出了下面的原型对照截图。

- 截图：`screenshots/03-current-error-detail.png`（错误详情整页）、`screenshots/04-current-problem-list.png`（错误页全部）。
- 详情页标题行（`.problem-title`）：`合成示例：技能输出格式不稳定。`——整段长文本直接当标题，且**没有**正文块（不存在 `.ed-detail` 对应的 DOM）。
- 同一段长文本同时出现在左栏问题卡主文本（`.problem-card-title`）与执行流问题卡（`.finding-reason`），图上卡片被长文本撑到宽度钳制上限。
- 结论：当前 UI 只有一级文本，原型是「短标题 + 描述正文」两级文本。

## 根因

`bad_cases` 表、`BadCase` / `SessionBadCase` 契约都只有 `reason` 一个长文本字段，05 §9 原型字段映射表没有把原型 `finding.title` / `finding.detail` 映射到接口字段；前端只能把 `reason` 当标题渲染。这是数据模型缺口，不是前端实现偏差。

修复方案：`bad_cases` 增加 `title VARCHAR(255) NOT NULL`，原 `reason` 列改名 `bad_case_description`（语义仍是描述正文，对外 DTO 字段名保持 `reason`）；详情页标题行渲染 `title`、新增正文块渲染 `reason`；列表卡与图上问题卡主文本改用 `title`。
