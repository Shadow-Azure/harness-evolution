# Agent Note: 第 4 步归因报告 ID 深链

Status: implemented

[English](2026-11-20-attribution-report-link.en.md) | 中文

## Problem

运行详情第 4 步「对象归因」把「归因报告 ID」与「来源 bad case」都渲染成纯文本。V2 原型在同一位置把它们设计成新窗口链接：报告 ID 打开该 bad case 的错误详情并停在「归因分析」页签，来源 bad case 打开「问题描述」页签。生产与 `main` 一致，问题不在构建或缓存。现场测量、生产与原型对照见 [#443](https://github.com/Shadow-Azure/harness-evolution/issues/443)。

只改模板修不好这个问题：错误详情的深链必须带 Session，而第 4 步 DTO（`StepAttributionRow`）只有 `bad_case_id` / `attribution_id`，没有 Session。设计文档只记录了第 4 步的列，没有写点击行为；组件测试也只断言文本与统计，所以原型里的交互在实现时丢失后没有回归拦住。

## Decision

- `StepAttributionRow` 增加必填 `session_id`。V2 取 `candidate.session_id`，legacy 取 `first.probe_session_id`；两者都是真实来源 Session，不从其它步骤反推。
- `StepAttribution.vue` 接收 `wid`，用 `badCaseDeepLink(wid, row.sessionId, row.badCaseId, tab, attributionId)` 渲染两列锚点：来源 bad case 用 `tab=desc`，报告 ID 用 `tab=attr` 且带 `at=row.attributionId`。锚点使用 `target="_blank"`、`rel="noopener noreferrer"`，保留完整 ID 作为可见文本，并补 `title` 与 `aria-label`。
- `RunStepContent.vue` 把已有的 `wid` 传给 `StepAttribution`；不新增上下文或请求。
- 组件测试锁定两列的 `href` / `target` / `rel` / `aria-label`；API 阶段测试锁定 V2 与 legacy 行的 `session_id`；`m10-06` E2E 锁定 6 行 12 个链接、href 与可聚焦性。
- 08 设计文档在「七步展示要点」与「交互」两处记录第 4 步的点击契约，避免下一次重排再次丢失。

## Alternatives considered

- **沿用 V2 原型的全局 `BAD_CASES` fixture 反查 Session**：原型可以用全局 fixture 按 case 反查，生产数据来自数据库，前端没有这张表；为了链接再维护一份镜像会制造第二个事实源。拒绝。
- **从前端已有的第 3 步 potential rows 反查 Session**：第 3 步分页 5 条且可能未加载，第 4 步 6 行以上时查不到；把两个步骤的加载顺序绑在一起也会让步骤切换更脆。拒绝。
- **新增按 `attributionId` 解析深链的 API**：多一次往返只为一个可直接随行返回的字段，且链接构造仍要在前端做。拒绝。
- **只修「归因报告 ID」，保留「来源 bad case」纯文本**：同一张表两列视觉与行为不一致，issue 的验收也要求来源列可点。拒绝。
- **给整行加点击或 `role="link"`**：会与单元格内文本选择、复制冲突，也不如原生锚点可聚焦、可新窗口。拒绝。

## Consequences

- 第 4 步的两列链接与第 3 步、错误列表共用 `badCaseDeepLink`，深链格式只有一处定义；错误详情页的 `at` 解析已有测试覆盖。
- 契约只增加一个必填字段，不改数据库、不改归因算法；旧客户端忽略额外字段不受影响。
- legacy 行使用持久化的 `probe_session_id`；没有 Session 的历史数据不会伪造链接。
- 新增的组件与 E2E 断言会在两列退回纯文本、`at` 丢失或 `target`/`rel` 被改坏时变红。
- 如果未来错误详情路由改变，必须同步 `badCaseDeepLink`；本次没有把 URL 拼装逻辑复制到组件里。
