# Agent Note: 运行详情已接纳 commit 按 Markdown 展示

Status: implemented

[English](2026-11-22-run-detail-commit-markdown.en.md) | 中文

## Problem

运行详情第 6 步的已接纳轮次把 `finalCommit.message` 直接插值进 `.commit`，按一行等宽文本展示。后端 `build_accepted_message()` 已经把 commit message 升级成多段 Markdown：首行 subject，随后 `## 问题`、`## 分析`、`## 改动`、`## 追溯`、`-` 列表、URL、`---` 与 `Harness-*` trailer。浏览器把换行折叠成空格，`##` 与 `---` 只能按字面出现，长 bad case ID 和 URL 把卡片撑满；问题不在数据或 git 历史，而在展示层与设计契约。

设计文档当时只给了一行 `finalCommit.message` 示例（`05 §3.6`），`08 §10.3` 只说要展示 amend 后的 commit，没有规定多段 Markdown 怎么显示；V2 原型则只放结构化摘要。三处各自成立，合起来就是生产截图里的原文倾倒。组件测试也只断言 hash 与 `Harness-Evaluated-Commit`，没有覆盖长 Markdown，所以回归可以全绿上线。

## Decision

- `StepIterations.vue` 把 `finalCommit.message` 拆成首行 subject 与其余正文：subject 单行省略并保留 `title` 全文，正文单独渲染。
- 默认收起：已接纳轮次只显示 12 位 hash + subject；正文非空时提供「查看完整 commit message / 收起」按钮，按 `roundId` 记录每个轮次的展开状态。单行旧 message 不显示按钮。
- 正文复用现有 `renderMarkdown(..., { images: false })`，用 `v-html` 写入 `.commit-message.markdown`；不引入第二个 Markdown 库，不开放 raw HTML，不渲染图片。scoped `:deep()` 补标题、列表、链接、行内代码、代码块与分隔线样式；正文最大高度 520px 并可滚动，长 URL 用 `overflow-wrap: anywhere` 而不是 `break-all`。
- `05 §3.6` 与 `08 §10.3` 同步契约：`finalCommit.message` 是完整 Markdown 正文，首行是 subject；展示层禁止按纯文本插值，旧单行 message 仍是合法输入。
- 组件测试补长 Markdown fixture 和折叠/展开断言；E2E fixture 的已接纳轮次改用同一形态的长 message，并在第 6 步冒烟里断言默认无字面标记、展开后标题/列表/链接可见。
- V2 原型的方案 A（默认收起 + 按需展开 + Markdown 渲染）已经先行落地，生产实现以它为视觉与交互基线。

## Alternatives considered

- **不折叠，直接把完整正文 Markdown 渲染**：拒绝。改动更小，但长 message 仍会把第 6 步撑高，后续轮次被推离首屏，与原型紧凑卡片的信息密度不一致。
- **只保留原型的结构化摘要，不展示完整正文**：拒绝。最贴原型，但会丢失 run/cluster/来源问题的追溯信息。
- **只加 `white-space: pre-wrap`**：拒绝。能保留换行，但列表、链接、标题和 trailer 仍是字面字符，不能兑现「按 Markdown 渲染」。
- **新引入 Markdown 组件或库**：拒绝。仓库已有经过测试的 `renderMarkdown()`（`html:false`、链接加固），新增依赖只增加包体与审查面。
- **改后端缩短 commit message**：拒绝。commit 正文是 git 历史与追溯的一部分，本 issue 只修展示层，不改生成逻辑或历史数据。

## Consequences

- 旧 run 的单行 message 仍按 subject 显示，不出现空正文或多余按钮；未接纳轮次行为不变。
- 长 message 默认收敛为一张紧凑卡片，完整正文需要一次明确点击；正文有 520px 上限，极长内容在卡片内滚动，不再无限撑高页面。
- 安全边界复用现有渲染器：raw HTML 被转义，外链自动带 `target="_blank"` 与 `rel="noopener noreferrer"`，commit 里的 Markdown 图片降级为 alt 文本。
- E2E fixture 的 `v2-round-1` 使用长 Markdown message，第 6 步冒烟与截图都基于这份可复现数据；生产运行 ID、Session 内容与生产截图不进入仓库。
- 不改 API、`packages/contracts`、数据库或 commit message 生成逻辑；问题 #482 在提出人确认整条流程无问题之前保持 open。
