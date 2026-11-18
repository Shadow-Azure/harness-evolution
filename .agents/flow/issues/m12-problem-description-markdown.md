# 问题描述正文按 Markdown 渲染

[English](m12-problem-description-markdown.en.md) | 中文

```yaml flow
kind: issue
id: m12-17
milestone: m12
depends: []
priority: P2
status: done
scope:
  - apps/web/**
  - tests/e2e/**
  - fixtures/**
  - plans/**
  - docs/**
  - .agents/notes/**
  - .agents/flow/**
adr:
  - ../../notes/implemented/feature/2026-11-18-problem-description-markdown.md
github:
  number: 363
  url: https://github.com/Shadow-Azure/harness-evolution/issues/363
```

## 背景

2026-11-18，用户在生产「Session 错误查看」页反馈：问题描述区块（原反馈截图红框）是一整段纯文本，长失败清单没有分组和换行，扫读困难。截图中的 `[SWE-bench] astropy__astropy-13398 · unresolved` bad case 把 4 个 F2P 失败和 6 个 P2P 回退用例挤在同一段里，只能逐字读到句尾；用例名也没有行内代码的视觉边界。

`bad_case_description` 是自由文本，外部报告/分析侧已经在按「状态 + 失败分组 + 用例清单」组织内容，但 HE 端按纯文本输出，HTML 把换行折叠成空格，Markdown 语法也不会生效。

### 现状链路

- 上报：外部系统写 `bad_cases.bad_case_description`，HE 在 `apps/api/app/db/crud/bad_cases.py` 原样映射成 `BadCase.reason`；[06 §4.1](../../../plans/fullstack-design/06-database-design.md) 约定描述正文「直接展示」。
- 展示：`ProblemDescription.vue` 的 `.problem-detail` 直接插值 `{{ problem.reason }}`（117–122 行）。
- 同页已有能力：归因「推导过程」通过 `apps/web/src/utils/markdown.ts` 的 `renderMarkdown` 渲染（markdown-it，`html:false`、`breaks:true`、`linkify:true`，外链统一 `target="_blank"` + `rel="noopener noreferrer"`），并配有 `.markdown` 排版（`AttributionReport.vue` 287–292 行、596 行起）。问题描述没有复用这条链路。
- 结果：多行、列表、代码片段、强调和链接都退化成一段平文；越长越不可读。

### 证据截图

**修改前 / 修改后（同一 case、同一 1440×1400 视口、浅色主题、2× DPR）**

[![问题描述 Markdown 修改前/后](https://github.com/Shadow-Azure/harness-evolution/releases/download/issue-markdown-prototype-evidence-20261118/problem-description-compare.png)](https://github.com/Shadow-Azure/harness-evolution/releases/download/issue-markdown-prototype-evidence-20261118/problem-description-compare.png)

原图：[修改前](https://github.com/Shadow-Azure/harness-evolution/releases/download/issue-markdown-prototype-evidence-20261118/problem-description-before.png) · [修改后](https://github.com/Shadow-Azure/harness-evolution/releases/download/issue-markdown-prototype-evidence-20261118/problem-description-after.png)

可下载的修改后原型：[prototype-problem-description-markdown.html](https://github.com/Shadow-Azure/harness-evolution/releases/download/issue-markdown-prototype-evidence-20261118/prototype-problem-description-markdown.html)。打开后登录任意演示账号，进入「Session 错误查看」并选择 `SWE-bench astropy-13398` 会话即可看到该 case。

说明：修改前使用当前上报的单行纯文本（与反馈的 SWE-bench 失败清单同构）；修改后使用同一用例的 Markdown 版描述，展示列表、行内代码与分组。两组截图都在修改前后的 V2 原型上截取，未进入生产代码。

## 目标

- 问题描述正文按 Markdown 渲染，列表、段落、行内代码、强调、链接、代码块有清晰层级。
- 保留单换行（`breaks:true`），让遗留的多行纯文本立即按行显示。
- 安全渲染：禁用原始 HTML，外链加固，不引入脚本执行面。
- 无 Markdown 语法的纯文本不回归：仍是普通段落，文字完整保留。
- 同步 V2 原型并留下修改前/后证据，供后续实现按同一信息架构落地。

## 设计依据

- [05 §3.4 bad case 详情](../../../plans/fullstack-design/05-api-design.md)：`reason` 的 DTO 语义与字段映射。
- [06 §4.1 bad_cases](../../../plans/fullstack-design/06-database-design.md)：`bad_case_description` 是描述正文，当前约定「直接展示」。
- [08 §7 错误详情页](../../../plans/fullstack-design/08-frontend-implementation.md)：错误详情的信息层级、问题描述 tab 与归因正文的 Markdown 边界。
- 现有实现：`apps/web/src/utils/markdown.ts` 与同页的 `AttributionReport.vue`。
- [V2 设计 §8 错误详情](../../../plans/ui-prototype-v2/design-v2.md)：一个 bad case × 多条归因的布局与问题描述 tab。
- [V2 原型](../../../plans/ui-prototype-v2/harness-evolution.html)：`FindingDescription` 与 `.ed-detail.markdown` 的排版基线。

## 实现内容

- **前端渲染**：`ProblemDescription.vue` 新增 `reasonHtml = computed(() => renderMarkdown(problem.reason))`，正文改为 `<div class="problem-detail markdown" data-testid="problem-detail" v-html="reasonHtml" />`，并补与 `AttributionReport` 相同的 eslint 注释说明。
- **安全边界**：复用现有 `renderMarkdown`，不新增 Markdown 依赖；`html:false` 已转义原始 HTML，`link_open` 已加固外链；问题描述关闭 Markdown 图片（降级为 alt 文本，避免外部加载）；不接语法高亮。
- **排版**：`.markdown` 基础样式与问题描述的字号/行高对齐（12.5px / 1.7），补 `p`、`ul/ol`、`li`、`code`、`pre` 的间距；行内代码用 `--mono` + `--bg-inset` chip，长用例名 `overflow-wrap:anywhere`，不撑破卡片；代码块等宽横向滚动；强调与链接使用现有 token。
- **空值/纯文本**：空描述返回空字符串，不渲染空段落；纯文本（无 Markdown 语法）输出与现在等价的文本内容，单换行按 `<br>` 保留。
- **原型**：`plans/ui-prototype-v2/harness-evolution.html` 的 `FindingDescription` 按同一约定渲染，并保留 SWE-bench 演示 case；生产实现与原型同构。
- **测试**：`ProblemDescription.test.ts` 增加 Markdown 列表、行内代码、硬换行、原始 HTML、外链属性的断言；`markdown.test.ts` 锁定 `breaks` 与转义行为；E2E 保持现有错误详情用例通过，必要时补一条 Markdown fixture 断言。
- **文档与 Note**：更新 `05`、`06`、`08` 的展示约定，新增 Agent Note 记录「为什么用 Markdown、为什么复用现有渲染器、为什么不接裸 HTML/语法高亮」。

## 实施步骤

1. 先写 `ProblemDescription.test.ts` 的失败用例，确认当前纯文本实现不能渲染列表/行内代码。
2. 在 `ProblemDescription.vue` 接入 `renderMarkdown`，补 `.problem-detail.markdown` 的 scoped `:deep()` 排版。
3. 跑聚焦单测、类型检查与 lint；补 `markdown.test.ts` 的换行/转义断言。
4. 更新 `plans/fullstack-design/05`、`06`、`08` 与 V2 设计文档，新增 Agent Note 并重录双语。
5. 用真实前端冒烟：种子数据中注入 Markdown 描述，截图并与 V2 原型同视口对比；差异回修。
6. 提交 PR、等 CI、按 `docs/review.md` 检视；处理检视意见后重跑冒烟与 CI。

## 依赖与交付边界

- 依赖：无。本 issue 不改 API、数据库列、契约类型或权限；`bad_case_description` 仍是自由文本，前端只改变展示。
- 数据侧格式约定是并行依赖：上游不改也能安全渲染现有纯文本（换行开始生效），但分组列表需要上游按 Markdown 输出；该约定写入 `06` 与 `05`。
- 交付边界：`ProblemDescription.vue`、对应测试/样式、原型、设计文档与 Note；不改 `AttributionReport.vue` 的 `reason` 纯文本与 `reasoning` Markdown 分工。

## 独立验证

```sh
pnpm --filter @harness/web test -- src/pages/errors/components/ProblemDescription.test.ts src/utils/markdown.test.ts
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e -- --pattern "m4 error detail"
```

- 预期：问题描述渲染 `<ul>/<ol>`、`<code>`、`<strong>`，换行保留；原始 HTML 不生成节点；外链带 `target="_blank"` 与 `rel="noopener noreferrer"`；纯文本描述文本内容不变。
- 人工验证：打开 V2 原型的 SWE-bench 演示 case，确认 F2P/P2P 分组列表和行内代码显示；与上方修改前截图对比。
- 冒烟：本地真实前端 + 临时数据目录，注入同一 Markdown 描述，截图与原型对比；不把临时数据或截图提交到代码仓。

## 验收标准

- 问题描述中的 Markdown 列表、行内代码、强调、链接和代码块按预期渲染。
- 单换行在正文中可见；多行纯文本不再折叠成一整段。
- 原始 HTML 不执行；外链加固；纯文本描述不回归。
- V2 原型包含同一演示 case，修改前/后截图与描述一致。
- PR 内含刷新后的 Before/After 截图、真实前端冒烟截图与原型对比，以及组件/工具函数测试。

## 门禁与 CI

- `pnpm --filter @harness/web test -- src/pages/errors/components/ProblemDescription.test.ts src/utils/markdown.test.ts`
- `pnpm typecheck:web`、`pnpm lint:web`
- `pnpm test:e2e -- --pattern "m4 error detail"`
- `pnpm verify:flow`、`pnpm test:gates`、`pnpm lint:docs`
- PR 标题与提交信息含 `(#363)`，检视按 `docs/review.md`。

## 非目标

- 不新增 Markdown 渲染库，不改变 `renderMarkdown` 的安全配置。
- 不把历史纯文本自动改写成 Markdown，不做格式识别/猜测。
- 不改 bad case 上报契约字段、数据库列或 API 结构；只明确展示格式约定。
- 不调整错误详情的信息架构、配色或其它区块；不改归因 `reason` 的纯文本渲染。
