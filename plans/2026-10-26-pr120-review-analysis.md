# PR #120 检视意见复核

## 结论

D1-D4 全部成立，均应在 PR #120 修复。D1、D2 属 Important，合并前必须处理；D3、D4 是严格的可见原型偏差，修复成本低，一并在同一 PR 收敛。

## D1 归因信息重复与顺序偏差

**Verdict：修复。**

设计依据：

- `plans/fullstack-design/08-frontend-implementation.md:424-429` 规定固定顺序：结论 → 非问题原因或分类+根因对象 → 问题描述 → 推导 → 来源。
- `plans/14-15-ui-prototype/harness-evolution.html:2029-2043` 的结论横幅只放“结论”、结论值和状态，不放原因、分类或根因对象。
- `plans/14-15-ui-prototype/harness-evolution.html:2044-2081` 把非问题原因、问题分类、根因对象放到结论后的独立正文块。

代码证据：

- `apps/web/src/pages/errors/components/AttributionReport.vue:102-108` 在非问题结论横幅内重复输出 `analysis.result.reason`，该字段又在 `:120-128` 输出。
- `apps/web/src/pages/errors/components/AttributionReport.vue:109-118` 在问题结论横幅内重复输出分类和根因对象，两者又在 `:144-156` 输出。
- `apps/web/src/pages/errors/Index.test.ts:238-241` 把根因对象出现在 `.conclusion` 固化成期望，掩盖了偏差。

修复边界：

- 结论横幅只保留“结论”、结论值，以及不重复正文的 kind/status 语义。
- 非问题原因、分类、根因对象只在固定顺序的第二步出现一次。
- 测试改为断言上述字段在 `.conclusion` 中不存在、在正文中出现且“非问题原因 → 推导”顺序正确。

## D2 ID 展示与深链交互不一致

**Verdict：修复。**

设计依据：

- `plans/fullstack-design/05-api-design.md:948` 要求真实 ID 在 UI 取前 8 位，tooltip 展示全量。
- `plans/fullstack-design/09-review-guide.md:15` 与 `:42-44` 要求真实 ID 点击后在新窗口打开并指定 tab。
- `plans/fullstack-design/08-frontend-implementation.md:302` 明确问题列表 ID 徽章点击调用 `window.open(badCaseDeepLink(...), "_blank")`。
- `plans/14-15-ui-prototype/harness-evolution.html:2000-2008` 的问题 ID 是独立链接，`target="_blank"`，问题描述落 `desc` tab。
- `plans/14-15-ui-prototype/harness-evolution.html:2060-2066` 的归因报告/来源问题 ID 是独立链接，`target="_blank"`，按目标落 `attr` 或 `desc` tab。

代码证据：

- `apps/web/src/pages/errors/components/ProblemDescription.vue:30-36` 取前 12 位且是不可点击的 `span`。
- `apps/web/src/pages/errors/components/AttributionReport.vue:181-191` 取前 12 位，并用当前窗口的 `RouterLink`，没有 `target`/`rel`。
- `apps/web/src/components/bad-cases/BadCaseList.vue:101-133` 虽显示前 8 位，但整卡是 `button`，ID 被包含在按钮内，无法作为独立新窗口链接。
- 仓库尚无 fullstack design 指定的 `apps/web/src/utils/badCaseId.ts`，短 ID 与深链构造分散。

修复边界：

- 新建纯函数模块 `utils/badCaseId.ts`，集中提供 `shortBadCaseId()` 与 `badCaseDeepLink()`；短 ID 固定 8 位，深链保留真实 ID 和显式 tab。
- 问题描述和来源问题改用新窗口 `<a>`，加 `title` 全量 ID、`target="_blank"`、`rel="noopener noreferrer"`。
- 问题卡 ID 必须成为独立可聚焦链接。卡片选择与 ID 新窗口不能嵌套交互元素：使用卡片容器承载视觉边框，兄弟节点分别承担“选择/定位按钮”和“ID 链接”，其他展示内容无点击语义；选择按钮覆盖卡片可点击区域，ID 链接提升层级并阻止冒泡。
- 组件测试锁定短 ID、href、target、rel、问题描述 tab 与来源问题 tab；E2E 通过 DOM 属性验证，不依赖真实弹出窗口。

## D3 问题标题与正文重复 reason

**Verdict：修复。**

设计依据：

- `plans/fullstack-design/09-review-guide.md:51` 要求问题描述展示 badCaseId、reason、状态、metadata facts 与上报对象，没有定义第二次 reason 正文。
- `plans/14-15-ui-prototype/harness-evolution.html:2000-2020` 中标题与 `finding.detail` 分离；当前 API 没有独立 detail 字段。

代码证据：

- `apps/web/src/pages/errors/components/ProblemDescription.vue:37-40` 在标题输出 `problem.reason`。
- `apps/web/src/pages/errors/components/ProblemDescription.vue:54-56` 又以正文原样输出同一字段。

修复边界：

- 删除重复正文段，reason 只保留在标题；facts、关联对象与降级诊断保持原顺序。
- 测试断言页面中该 reason 只出现一次。

## D4 未分析空态文案偏离原型

**Verdict：修复。**

设计依据：

- `plans/fullstack-design/08-frontend-implementation.md:420` 要求未分析时显示“尚未分析”空态。
- `plans/14-15-ui-prototype/harness-evolution.html:2026-2034` 的完整用户文案是“该错误还没有归因分析，尚不能判断是否为问题。”

代码证据：

- `apps/web/src/pages/errors/components/AttributionReport.vue:92-100` 在结论横幅内使用“外部归因系统尚未写入结果”，既偏系统术语，也未按原型把说明放在横幅后的空态块。
- `apps/web/src/pages/errors/Index.test.ts:319-328` 锁定的是当前偏差文案。

修复边界：

- 结论横幅仅保留“尚未分析”和“未分析”状态。
- 横幅后使用原型文案 `该错误还没有归因分析，尚不能判断是否为问题。`。
- 测试锁定新文案，并断言结论横幅中不存在该说明。

## 回归策略

按 TDD 先新增/修改失败测试，再改组件：

- `apps/web/src/utils/badCaseId.test.ts`：短 ID、深链编码和 desc/attr。
- `apps/web/src/pages/errors/Index.test.ts`：D1 固定顺序与去重、D2 两个新窗口链接、D3 reason 唯一、D4 原型文案。
- `apps/web/src/components/bad-cases/BadCaseList.test.ts` 或现有问题列表测试：ID 链接独立于选择按钮，点击链接不触发行选择。
- `tests/e2e/m4-error-detail.test.mjs`：实际渲染的 ID 为 8 位，链接带正确 href/target/rel，点击卡体仍只更新 URL。

修复后必须复跑 Web 单测、typecheck、lint、错误详情真实 Chrome E2E，并再次执行 Computer Use smoke/reporting。
