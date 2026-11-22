# 进化对象配置页内容列固定在 1080px 导致 8 列表格横向溢出

[English](bugfix-target-config-page-width.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-15
milestone: bugfix
depends: []
priority: P2
status: ready
scope:
  - apps/web/**
  - tests/e2e/**
  - plans/**
  - .agents/**
adr: []
github:
  number: 498
  url: https://github.com/Shadow-Azure/harness-evolution/issues/498
```

## 背景

生产「自进化 → 进化对象配置」页（`/workspaces/<wid>/evolution/targets`）在 1408×788 CSS 视口下，8 列表格自然宽约 1071px，而内容列 `.workspace-main .evolution-page-frame` 固定为 1080px，表格滚动容器 `clientWidth` 只有 996px，最右侧「操作」列被横向滚动容器裁切；1920 视口下内容列仍是 1080px，左右各空 420px。现场测量、原型对照与浏览器内候选修复见 GitHub #498。

## 目标

- 进化对象配置页按 V2 原型的 1720px 内容容器显示：1408 视口下内容面板 1360px，8 列完整显示，表格不再出现横向滚动条。
- 1920 视口下内容列在 1720px 处封顶并居中，不再浪费页宽。
- 1024 及更窄视口保留表格自身的横向滚动兜底；不改变列、字段、排序、操作与数据口径。

## 设计依据

- [08 §9.5 进化对象配置页](../../../plans/fullstack-design/08-frontend-implementation.md#L728-L765)：页面按 V2 设计有 8 列（对象类型、对象名称、仓库、子目录、基线、测试工程、状态、操作），比原型的 6 列更宽。
- [V2 原型 `.evo-app .wrap`](../../../plans/ui-prototype-v2/harness-evolution.html#L606)：`width: min(100%, calc(1720px / var(--ui-zoom, 1)))`、`max-width: none`、`padding: 20px 24px 64px`；1408 视口下内容面板宽 1360px。
- [V2 原型对象配置面板](../../../plans/ui-prototype-v2/harness-evolution.html#L5684)：表格在 `.wrap` 内按可用宽度铺开，不出现横向滚动。

## 实现内容

- `apps/web/src/styles/main.css`：共享页宽改为 `min(var(--evolution-page-max-width, 1080px), 100%)`，并在 `.target-config-page` 上设 `--evolution-page-max-width: 1720px`；默认 1080px 继续作用于自进化列表与空间管理页，≤640px 的 `width: 100%` 分支保持有效。
- `tests/e2e/m5-target-config.test.mjs`：1408 视口断言页面宽 1408、内容宽 1360、表格 `scrollWidth === clientWidth` 且操作列完整可见；补 1920 视口断言页面宽 1720、内容宽 1672、表格不横向溢出；1024 视口保留横向滚动兜底。
- `tests/e2e/m5-run-list.test.mjs` 与 `tests/e2e/m7-09-workspace-admin.test.mjs`：继续断言自进化列表与空间管理页保持 1080px。
- 新增 Agent Note 记录「按页放开 1720px、其余页仍保持 1080px」的决策与边界。

## 实施步骤

1. 先改 E2E 断言，在 1080px 基线上复现表格溢出。
2. 在共享样式为目标配置页加 1720px 页宽规则。
3. 本地起应用，在 1408×788、1920×1080、1024×768 对照 V2 原型与 Before/After 截图。
4. 跑聚焦 E2E、类型检查、lint 与流程门禁；PR 附 Before/After 证据。

## 依赖与交付边界

- 依赖：无。
- 交付边界：只改目标配置页页宽与对应回归测试；不统一自进化列表、空间管理页的 1080px 页宽。

## 独立验证

```sh
pnpm test:e2e -- "m5 target configuration"
pnpm test:e2e -- "m5 run list"
pnpm test:e2e -- "m7-09 workspace-admin"
pnpm typecheck:web
pnpm lint:web
pnpm verify:flow
pnpm test:gates
```

- 1408×788：`.target-config-page` 宽 1408、内容宽 1360；`.target-table` 的 `scrollWidth === clientWidth`，「编辑 / 停用 / 删除」完整可见。
- 1920×1080：`.target-config-page` 宽 1720 且居中、内容宽 1672；表格不横向溢出。
- 1024×768：表格保留横向滚动，页面本身不出现横向溢出。
- 上述命令全绿。

## 验收标准

- 1408×788 下内容列由 1080px 扩到 1408px，内容面板 1360px，与 V2 原型同视口一致；8 列完整显示，操作列不被裁切，表格底部无横向滚动条。
- 1920×1080 下页宽 1720px 居中；1024 及更窄视口表格可横向滚动，页面无横向溢出。
- 自进化列表、空间管理页的页宽与布局不变（run-list 与 m7-09 的页面宽度断言覆盖）。
- Before/After 截图同场景、同视口、同主题、同数据；Before 标注基线提交。
- 校验命令全绿。

## 门禁与 CI

- `pnpm test:e2e -- "m5 target configuration"`、`pnpm typecheck:web`、`pnpm lint:web`。
- `pnpm verify:flow`、`pnpm test:gates`。
- CI 全绿后交付人工检视；本 PR 由人合并。

## 非目标

- 不修改表格列、字段、操作按钮、排序、数据口径与接口。
- 不把自进化列表、空间管理页统一到 1720px。
- 不改 V2 原型、设计 token 或其他页面布局。
- 不提交生产截图、Session 内容或凭据。
