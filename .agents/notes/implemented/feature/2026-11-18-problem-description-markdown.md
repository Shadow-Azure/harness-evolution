# Agent Note: 问题描述正文按 Markdown 渲染

Status: implemented

[English](2026-11-18-problem-description-markdown.en.md) | 中文

## Problem

`BadCase.reason`（`bad_cases.bad_case_description`）是错误详情「问题描述」tab 的正文。它来自外部上报或轨迹分析，内容经常是「状态 + 失败分组 + 用例清单」：F2P 失败、P2P 回退、逐个测试名。当前 `ProblemDescription.vue` 直接插值 `{{ problem.reason }}`，浏览器把换行折叠成空格，列表、行内代码和强调都不生效；一条 SWE-bench unresolved case 会变成三段连续文字，失败用例只能逐字扫描。

同页的归因「推导过程」已经有一条安全 Markdown 链路：`utils/markdown.ts` 用 markdown-it 渲染，`html:false`、`breaks:true`、`linkify:true`，`link_open` 统一补 `target="_blank"` 与 `rel="noopener noreferrer"`；`AttributionReport.vue` 用 `v-html` 消费并配了 `.markdown` 排版。问题描述没有复用这条链路，两者都需要同样的 Markdown 排版与安全边界（归因推导过程由服务端模板生成，问题描述来自外部上报）。

只加 CSS `white-space: pre-wrap` 可以救回换行，但救不回列表、行内代码和强调；而让前端识别「这是不是一个失败清单」再自动排版，会把展示层变成猜测器，且无法覆盖代码块、链接等常见描述内容。

## Decision

- `ProblemDescription.vue` 新增 `reasonHtml = computed(() => renderMarkdown(problem.reason))`，正文用 `v-html` 写入 `problem-detail markdown`，eslint 注释与 `AttributionReport` 保持一致。复用现有渲染器，不新增依赖。
- 在 scoped CSS 中用 `:deep()` 补 `.problem-detail.markdown` 的 `p`、`ul/ol`、`li`、`code`、`pre`、`strong`、`a` 排版：字号/行高沿用 12.5px / 1.7；行内代码用 `--mono` + `--bg-inset` chip；长测试名 `overflow-wrap:anywhere`；代码块等宽横向滚动；不接语法高亮。
- 数据侧约定写进 `06 §4.1` 与 `05 §3.4`：`bad_case_description` 允许并鼓励 Markdown；失败分组用小标题、用例名用行内代码、逐条列表；历史纯文本不迁移，`breaks:true` 让已有换行立即生效。
- 归因 `AttributionReport.reason` 仍是纯文本，`reasoning` 仍是 Markdown，两者分工不变。
- V2 原型 `FindingDescription` 同步为同一约定，并加入 SWE-bench 演示 case；生产实现的视觉以该原型为基线。

## Alternatives considered

- **只加 `white-space: pre-wrap`**：拒绝。能保留换行，但列表、行内代码、强调、代码块仍是一堆字符；无法兑现「Markdown 渲染」。
- **前端识别失败清单并自动格式化**：拒绝。展示层不应该猜测自由文本的语义；同一段文字在不同上报方写法不同，规则会漂移，也无法安全处理代码块和链接。
- **新引入一个 Markdown 组件/库**：拒绝。同页已有经过测试的 `renderMarkdown`，安全配置和链接加固都已就位；新增依赖只增加包体和审查面。
- **把归因 `reason` 也改成 Markdown**：拒绝。它与 `reasoning` 的语义分工是「结论说明 vs 推导过程」，本 issue 只改问题描述，不扩大归因契约。
- **在入库时把纯文本转成 Markdown**：拒绝。转换不可逆且会污染外部权威数据；展示层只负责安全渲染，格式约定交给上报侧。

## Consequences

- 已有纯文本描述不会变差：没有 Markdown 语法时仍渲染为普通段落，单换行按 `<br>` 显示；但一条没有换行的长平文仍然是一条长平文，分组可读性需要上游按 Markdown 输出。
- 安全边界复用现有配置：原始 HTML 被转义，外链加固；问题描述关闭 Markdown 图片（降级为 alt 文本，避免外部加载）；不接语法高亮，代码块只做等宽滚动。
- 组件测试需要覆盖「列表/行内代码/硬换行/原始 HTML/外链」；`markdown.test.ts` 锁定 `breaks:true` 与转义行为，防止未来改配置时静默回归。
- V2 原型多了一条 SWE-bench 演示 session/case（`BC-HC-027`），会话数与 bad case 计数会比之前多 1；它只用于设计评审，不进入生产数据。
- 数据侧格式约定是并行的：在外部上报/分析侧按 Markdown 输出之前，UI 只能保证「已经带 Markdown 或换行的描述」正确显示，不能凭空生成失败分组。
