# 运行详情第 6 步把 commit Markdown 正文当纯文本展示，与 V2 原型不一致

[English](bugfix-run-detail-commit-markdown.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-13
milestone: bugfix
depends:
  - m21-01
priority: P2
status: ready
scope:
  - apps/web/**
  - plans/ui-prototype-v2/**
  - plans/fullstack-design/**
  - tests/e2e/**
  - .agents/**
adr: []
github:
  number: 482
  url: https://github.com/Shadow-Azure/harness-evolution/issues/482
```

## 背景

### 问题场景

2026-11-22，用户在生产「自进化 → 运行详情」第 6 步「迭代优化」中展开一个已接纳轮次，红框区域把 `finalCommit.message` 整段原样铺在卡片里：`evolve(...)` 标题之后直接出现 `## 问题`、`## 分析`、`## 改动`、`## 追溯`、`---` 与 `Harness-*` trailer，`1.` 编号、长 bad case ID、URL 和换行全部挤成一段连续文本。同一区块上方的 `Harness-Evaluated-Commit` 与 12 位 hash 显示正常，问题只出在 commit 正文。

生产现场（红框为用户标注的检查位置）：

![生产运行详情第 6 步：已接纳 commit 的 Markdown 正文被当纯文本展示](https://github.com/Shadow-Azure/harness-evolution/releases/download/run-detail-commit-markdown-evidence-20261122/prod-commit-raw.png)

复现路径：生产「自进化」→ 历史记录 → 任一已完成或已接纳轮次的运行 → 运行详情 → 第 6 步「迭代优化」→ 展开状态为「已接纳」的轮次。只要该轮次的 `finalCommit.message` 是新版多段 Markdown（`build_accepted_message`），就会复现；不依赖某个特定运行或某个特定 bad case。

### 现场观察

- `##`、`---`、`-`、`1.` 等 Markdown 标记按字面显示，没有被解析成标题、分隔线、列表或链接。
- commit 正文里的换行没有保留：`## 问题`、`## 分析`、`## 改动` 与各条 `来源问题` 全部挤在同一个段落里，长 bad case ID 与 URL 又把行宽撑满，可读性接近日志倾倒。
- 整块使用等宽字体和 `word-break: break-all`，正文、hash、标题没有视觉层级；卡片高度随 commit 消息长度增长，长消息会把第 6 步后续轮次推到很远。
- 问题只在展示层：git commit 本身、run 分支、评测与接纳结果都正常，复制 commit message 也能拿到完整 Markdown。

### V2 原型对照

V2 原型对应位置 `plans/ui-prototype-v2/harness-evolution.html#L5435` 没有把完整 commit 正文塞进卡片。它用 `commit <短 hash>　evolve(<target>): <title>` 作为标题行，再用 `cluster:`、`cases:`、`phenomenon:` 三行输出结构化摘要；`.commit .cline` 只声明 `white-space: pre-wrap`（`#L807`），也没有 Markdown 解析器。也就是说，原型的处理是「有边界的结构化摘要」，不是「把 Markdown 原文原样展示」。

V2 原型第 6 步已接纳轮次的对应区块：

![V2 原型第 6 步：已接纳 commit 使用结构化摘要，不展示完整 Markdown 正文](https://github.com/Shadow-Azure/harness-evolution/releases/download/run-detail-commit-markdown-evidence-20261122/proto-commit-closeup-2x.png)

同场景的原型整页上下文（保留评测对比与后续轮次位置）：

![V2 原型第 6 步整页：commit 块只占一个紧凑卡片，后续轮次仍在首屏附近](https://github.com/Shadow-Azure/harness-evolution/releases/download/run-detail-commit-markdown-evidence-20261122/proto-commit.png)

生产与原型的分歧有两层：

1. **信息量**：原型只展示 commit 标题与聚类摘要；生产展示完整正文（问题、分析、改动、追溯、trailer），信息更多但没有任何收敛。
2. **格式**：原型至少用 `pre-wrap` 保住了三行摘要的换行；生产的 `.commit` 没有 `white-space`，正文里的换行被 HTML 折叠，Markdown 结构完全丢失。

### 根因分析

1. **后端已经把 commit message 升级成完整 Markdown**。`apps/api/app/service/evolution/git_candidate.py#L108-L147` 的 `build_accepted_message()` 用 `subject + _message_sections() + "---\n" + trailers` 拼出多段正文；`_message_sections()`（`#L753-L773`）固定输出 `## 问题`、`## 分析`、`## 改动`、`## 追溯`，并插入 `-` 列表、URL 与 `Harness-*` trailer。`apps/api/app/service/evolution/stages.py#L1071-L1078` 再把数据库里的 `round.commit_message` 原样映射成 `finalCommit.message`，契约 `StepFinalCommit.message` 只是普通 `string`，没有任何「这是一段短标题」的约束。
2. **前端仍按一行短标签渲染它**。`apps/web/src/pages/evolution/components/StepIterations.vue#L261-L264` 用 `{{ round.finalCommit.message }}` 文本插值，没有调用 Markdown 渲染；`.commit` 样式（`#L469-L479`）只有等宽字体和 `word-break: break-all`，没有 `white-space: pre-wrap`，所以 Markdown 的换行被折叠成空格，`##` 与 `---` 只能按字面出现。即使补上 `pre-wrap`，也只是「保留换行的原文」，不是 Markdown 渲染。
3. **设计契约没有定义这段 message 的展示形态**。`plans/fullstack-design/05-api-design.md#L422` 的 `finalCommit.message` 示例是一行 `evolve(deep-research@v2.0.0): 修复检索索引未校验导致的越界读取`；`plans/fullstack-design/08-frontend-implementation.md#L823` 只要求「展示 amend 后的 commit」，没有说明 message 已是多段 Markdown、也没有规定标题/正文/摘要的处理。于是后端按 Markdown 写、前端按单行文本读、原型按结构化摘要画，三处各自成立，合起来就是截图里的原文倾倒。
4. **测试没有覆盖长 Markdown**。`apps/web/src/pages/evolution/components/RunDetailConformance.test.ts#L427-L458` 只断言 `Harness-Evaluated-Commit` 与短 hash 出现，没有 fixture 覆盖 `##` 标题、列表、链接和换行，也没有折叠/展开行为断言；因此该回归可以全绿进入生产。

### 影响

- 第 6 步已接纳轮次的核心结果不可读：用户无法快速看出「哪个 cluster、为什么接纳、改了哪个文件、追溯到哪个 run」，只能在一大段等宽文本里找关键词。
- 长 commit message 会把后续轮次和底部内容推离首屏，增加滚动成本；在窄视口下 `break-all` 还会把 URL 和 ID 切得难以复制。
- 不影响数据、评测、推送与 git 历史；这是展示层与设计契约的偏差。

## 目标

- 已接纳轮次的 commit 区块恢复为可扫描结构：保留 12 位 hash 与 `Harness-Evaluated-Commit`，标题行显示 commit subject（`message` 第一行），不再把 `##`、`---`、`-` 当普通文本展示。
- commit 正文按 Markdown 渲染：`##`/`###` 变标题、`-` 变列表、URL 变可点击链接、`---` 变分隔线；正文默认收敛，用户需要时再展开完整内容，展开后仍保持 Markdown 结构。
- 与 V2 原型的信息架构一致：默认视图接近原型的紧凑 commit 卡片（hash + subject + 聚类事实），完整 message 作为可展开的补充，而不是主视图。
- 不改变 API、契约、后端 commit message 生成逻辑与既有 run 数据；旧 run 的短 message 仍正常显示。
- 用组件测试与截图对照锁住「长 Markdown 不再按纯文本展示」与「默认收起、展开可见」。

## 设计依据

- [08 §10.3 Step6 迭代卡](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#103-step6-迭代卡)：展开内容顺序为来源 bad case → patch → candidate → 推送 → 评测 → 最终 commit / 拒绝说明；已接纳要展示 amend 后的 commit 与 `Harness-Evaluated-Commit`。
- [05 §3.6 迭代步骤契约](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/05-api-design.md#L422)：`finalCommit = { hash, message }`；当前示例只有一行 subject，正文形态需要在本 issue 中补清。
- [V2 原型第 6 步已接纳 commit](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html#L5435)：`commit <hash>　evolve(...)` + `cluster:` / `cases:` / `phenomenon:` 的紧凑摘要。
- [V2 原型 commit 样式](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/harness-evolution.html#L804-L807)：绿色 commit 卡、hash 高亮、`cline` 使用 `white-space: pre-wrap`，没有 Markdown 解析。
- [现有安全 Markdown 渲染器](https://github.com/Shadow-Azure/harness-evolution/blob/main/apps/web/src/utils/markdown.ts#L44-L64)：`renderMarkdown()` 使用 markdown-it，`html: false`，链接强制 `target="_blank"`、`rel="noopener noreferrer"`；已被 `ProblemDescription.vue` 与 `BadCaseList.vue` 使用。本 issue 复用该入口，不引入第二套 Markdown 库。
- [m21-01 运行详情重排](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/flow/issues/m21-run-detail-prototype-alignment.md)：第 6 步沿用 V2 原型轮次卡的信息顺序；本 issue 只修 commit 展示，不回退其字段与层级。

## 实现内容

- `apps/web/src/pages/evolution/components/StepIterations.vue`：
  - 从 `round.finalCommit.message` 拆出 subject 与正文：subject 取第一行（无换行时整段即 subject），正文取剩余部分并去掉首尾空行；subject 用单行省略 + `title` 保留全文。
  - 标题行继续显示 12 位 hash 与 subject；`Harness-Evaluated-Commit` 行保持不变。
  - 正文用 `renderMarkdown(commitBody, { images: false })` 渲染到 `.commit-message.markdown` 容器；`v-html` 只接收该函数输出，不拼接任何未转义的用户文本。
  - 默认收起：新增按 `round.roundId` 记录的展开集合；正文非空时显示「查看完整 commit message」/「收起」切换按钮；正文为空或只有 subject 时不显示切换按钮。
  - 样式：给 `.commit-message` 增加 `h2`/`h3`、`p`、`ul`/`ol`、`li`、`a`、`code`/`pre`、`hr` 的 scoped 样式（参考 `BadCaseList.vue` / `ProblemDescription.vue` 的现有 markdown 样式）；`.commit` 不使用 `word-break: break-all` 处理正文，改为 `overflow-wrap: anywhere`，hash 保持不换行；正文区最大高度与滚动策略按原型紧凑卡片的视觉密度确定，避免长消息无限撑高页面。
  - 保留「未接纳」分支原样：拒绝轮次仍显示「candidate 已删除，run 分支保持不变」并且不展示 commit hash。
- `plans/ui-prototype-v2/harness-evolution.html`：
  - 在已接纳轮次的 commit 卡片中补一个「完整 commit message（Markdown）」折叠示例：默认只显示原型现有的 4 行摘要，展开后展示 2–3 段 Markdown（标题、列表、链接）对应的渲染样式，确保原型能验收「收起 + 展开 + Markdown 渲染」。
  - 若评审认为原型不应增加交互，则至少把 `cline` 的说明改为「摘要，不展示完整正文」，并在设计文档中记录生产多出的展开能力；两种选择在 PR 中只能保留一种。
- `plans/fullstack-design/05-api-design.md` / `08-frontend-implementation.md`：
  - 将 `finalCommit.message` 的说明改为「amend 后的完整 commit message（Markdown）」；08 §10.3 补一句：默认展示 subject + 聚类摘要，完整正文折叠后用 Markdown 渲染，禁止按纯文本插值。
  - 若本 issue 选择保留原型摘要作为唯一视图，则同步说明「不展示完整正文」，并删除本 issue 的展开验收项。
- 测试：
  - `apps/web/src/pages/evolution/components/RunDetailConformance.test.ts`：新增一个包含 `## 问题`、列表、URL、`---` 与 trailer 的 `finalCommit.message` fixture；断言默认视图不出现字面 `##`/`---`，标题、列表与链接节点存在；点击切换后完整正文可见，再点收起后隐藏；断言 hash 与 `Harness-Evaluated-Commit` 仍在。
  - 如现有 E2E 能种入已接纳轮次，补一条第 6 步展开用例：长 Markdown 不产生横向滚动，页面仍可滚动到后续轮次。

## 实施步骤

1. 在 `StepIterations.vue` 增加 subject/正文拆分、展开状态与 `renderMarkdown` 渲染，先只改已接纳分支；跑聚焦组件测试确认短 message 不回归。
2. 补 `.commit-message` 的 Markdown 样式与长文本换行/滚动约束，确认 commit hash、`Harness-Evaluated-Commit` 和「未接纳」分支不受影响。
3. 更新 `RunDetailConformance.test.ts` fixture 与断言；必要时补 E2E。
4. 更新 V2 原型对应 commit 卡与 05/08 设计文档；两侧 prototype/design 的说明保持一致。
5. 用合成 fixture 在本地生产同构页面抓 Before / After 截图（同视口、同主题、同一已接纳轮次），并附 V2 原型对应区块；Before 明确标注当前基线提交。
6. 运行聚焦单测、类型检查、lint、E2E、`verify:flow` 与文档门禁；PR 描述附截图、验证命令与限制。

## 依赖与交付边界

- 依赖：m21-01（运行详情已按 V2 原型重排；本 issue 只修第 6 步 commit 展示，不回退其卡片顺序、字段集与页签）。
- 交付边界：`apps/web` 的运行详情展示组件、对应组件测试/E2E、V2 原型与 05/08 设计文档；不改 API、`packages/contracts`、数据库、git commit message 生成、评测与接纳流程。
- 不重写历史 commit，也不要求旧 run 的 `finalCommit.message` 迁移；旧的一行 message 仍按 subject 显示。
- 不把生产运行 ID、Session 内容、生产截图或凭据写入仓库；截图证据放 Release / PR 描述，仓库只保留可复现的 fixture 与测试。

## 独立验证

```sh
pnpm --filter @harness/web exec vitest run src/pages/evolution/components/RunDetailConformance.test.ts
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e -- "m10-06"
pnpm verify:flow
pnpm lint:docs
```

- 组件测试 fixture 使用含 `## 问题`、`-` 列表、`https://example.com`、`---` 与 `Harness-Evaluated-Commit` 的多行 message：默认视图的 `.commit` 文本不包含字面 `##` 或 `---`，`.commit-message h2`、`li`、`a[href]` 存在；点击「查看完整 commit message」后正文节点可见，再点「收起」后隐藏；短 message（单行）不显示切换按钮。
- 在生产同构页面的 1500×900 视口、浅色主题下，已接纳轮次默认只显示 hash + subject + 摘要；展开后标题、列表、链接按 Markdown 呈现；页面无横向滚动，可继续滚动到后续轮次。
- 与 V2 原型同视口对照：默认视图的信息密度与原型 commit 卡片一致；展开后的 Markdown 标题/列表/链接与设计文档描述一致。
- 现有 `Harness-Evaluated-Commit`、12 位 hash、候选 ref/commit、评测对比与「未接纳」说明的断言不回归；`verify:flow` 与 `lint:docs` 全绿。

## 验收标准

- 生产运行详情第 6 步已接纳轮次不再出现 `## 问题`、`## 分析`、`---` 等字面 Markdown 标记；换行不再被折叠成一段。
- 默认视图与 V2 原型一致：hash + commit subject + 聚类摘要，commit 正文默认收起；提供可发现的「查看完整 commit message」入口，展开后内容按 Markdown 渲染且链接可点击。
- 长 commit message 不撑破卡片、不产生横向滚动；第 6 步后续轮次与页面底部仍可正常到达。
- 旧 run 的单行 `finalCommit.message` 正常显示为 subject，不出现空正文或多余切换按钮；「未接纳」轮次行为不变。
- 不改 API/契约/后端；组件测试覆盖长 Markdown 与折叠展开，E2E 覆盖第 6 步回归（如现有 fixture 不具备已接纳轮次，则在组件测试覆盖并在 PR 说明 E2E 限制）。
- PR 附同场景、同视口、同主题的 Before / After 截图（Before 标注基线提交），以及 V2 原型对应区块截图；不把生产截图提交进仓库。
- 最终验收由提出人确认：在提出人确认整条流程暂时没有发现问题之前，本 issue 不关闭。

## 门禁与 CI

- 单测与覆盖率：`pnpm test:web`（至少覆盖 `RunDetailConformance.test.ts`）。
- 类型与 lint：`pnpm typecheck:web`、`pnpm lint:web`。
- E2E：`pnpm test:e2e -- "m10-06"`，必要时新增本 issue 的第 6 步用例。
- 流程：`pnpm verify:flow`；提交与 PR 标题带 `(#<本 issue 编号>)`。
- 文档：改动 V2 原型或 05/08 设计文档后运行 `pnpm lint:docs`；若改动常驻文档的中英配对，补跑 `pnpm record:i18n` 与文档门禁。
- CI 全绿后交付人工检视；本 PR 由人合并。

## 非目标

- 不改后端 commit message 的生成结构、section 文案、trailer 或 git amend / push 行为。
- 不改 API、`packages/contracts`、数据库字段或历史 run 数据；不要求为旧 run 回填正文。
- 不引入新的 Markdown 库、不开启 raw HTML、不渲染 commit message 中的图片；继续使用现有 `renderMarkdown()` 安全配置。
- 不重排第 6 步其他区块（来源 bad case、patch、candidate、推送、评测），不改第 1–5/7 步与执行日志。
- 不把完整 commit message 直接铺在默认视图里，也不以 `pre-wrap` 作为「渲染完成」。
- 不把生产运行 ID、Session 内容、生产截图或凭据写入仓库。
