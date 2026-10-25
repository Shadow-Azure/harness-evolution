# 前端壳层与设计令牌对齐交互原型

[English](m2-ui-prototype-alignment.en.md) | 中文

```yaml flow
kind: issue
id: m2-09
milestone: m2
depends: []
priority: P0
status: done
scope:
  - apps/web/**
  - tests/**
  - scripts/**
  - plans/**
  - reports/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
  - .github/workflows/ci.yml
  - package.json
  - pnpm-lock.yaml
adr: []
github:
  number: 92
  url: https://github.com/Shadow-Azure/harness-evolution/issues/92
```

## 背景

当前共享壳层使用近黑背景、`Harness Lens` 品牌、胶囊式导航和开发态健康状态胶囊；它与已确认的交互原型视觉基准不一致。原型与 `D16` 明确要求首版采用亮色主题：浅灰页面、白色卡片、56px 顶栏、`Harness Evolution` 品牌、下划线式分区导航和以蓝/紫/橙/红区分业务状态。登录、强制改密、空态和全局错误等已存在页面也会继承同一套壳层，因此需要先修复视觉基线，避免后续领域页面继续放大偏差。

## 目标

- 从原型原样移植亮色设计令牌、字体栈和 mono 字体语义，并保持现有语义 token 的可复用性。
- 将 TopNav、登录/强制改密、全局三态和 Sessions/Errors/Evolution 占位页对齐原型的信息层级、颜色、间距与交互。
- 在 1408px 和 390px 视口保留现有无障碍、响应式、鉴权和错误恢复能力，并用真实浏览器截图对照原型。

## 设计依据

- [原型最终验收基准](../../../plans/14-15-ui-prototype/harness-evolution.html)
- [03 前端架构 §9 设计令牌](../../../plans/fullstack-design/03-frontend-architecture.md)
- [08 前端实现 §1、§4、§12、§13](../../../plans/fullstack-design/08-frontend-implementation.md)
- [D16：首版只做亮色，视觉以原型令牌为准](../../../plans/fullstack-design/README.md)

## 实现内容

- 把原型 `:root` 的 `--bg / --bg-panel / --bg-card / --bg-inset / --border / --text / --text-dim / --text-faint / --blue / --green / --orange / --red / --purple / --cyan / --mono` 作为唯一颜色源，并映射到现有语义 token。
- 顶栏使用 56px 亮色面板、渐变方形标记、`Harness Evolution` 品牌、Sessions/Errors/Evolution 下划线式导航和右侧用户/演示状态；移除与原型的 `Harness Lens`、`Vue shell`、胶囊导航和开发态 API 状态胶囊不同的呈现。
- 登录、强制改密、Loading/Empty/Error/NotFound 和三个占位页改用原型的白色卡片、浅灰页面、13px 正文字号、紧凑间距及蓝/紫/橙/红状态语言。
- 保留 Element Plus 仅承载表单/消息控件，不自研替代其行为；业务布局和视觉组件继续自研。
- 增加设计令牌契约测试、关键组件测试和真实 Chrome 视觉证据，覆盖 1408px 与 390px。

## 实施步骤

1. 先写 token、TopNav、登录/改密、空态和窄视口视觉回归的失败测试。
2. 移植原型令牌并重构共享壳层与状态组件样式。
3. 跑单元、E2E、bundle/style 门禁，对照原型截图修正差异。
4. run Computer Use smoke，保存 before/after 证据并确认控制台清洁。

## 依赖与交付边界

- 依赖：无
- 交付边界：只对齐当前已存在的壳层、认证页、占位页和共享状态组件；真实 Sessions 列表、错误详情、执行流图和自进化业务页仍由各自 milestone issue 交付。

## 独立验证

```sh
pnpm test:web -- app-shell auth states
pnpm test:e2e -- m1-shell
pnpm typecheck:web
pnpm lint:web
pnpm build
pnpm verify:web-style
pnpm verify:bundle
```

- 设计令牌与原型颜色/字体值一致；登录、改密、三入口和空态在 1408px 与 390px 均无控制台错误、无横向溢出，视觉层级与原型一致。

## 验收标准

- 页面背景为 `#f4f5f7`，面板为 `#fafbfc`，卡片为白色，正文为 `#212832`，品牌与分区状态使用原型蓝/紫/橙/红语义。
- 顶栏高度 56px，品牌名为 `Harness Evolution`，主导航为下划线式激活态，不再出现 `Harness Lens`、`Vue shell` 或胶囊式主导航。
- 登录/强制改密、Loading/Empty/Error、Sessions/Errors/Evolution 占位页均使用统一亮色视觉，不提前展示伪造领域数据。
- 真实 Chrome 在 1408×900 与 390×844 下无 warning/error、无横向滚动，导航、用户菜单、退出和错误重试可用。
- before/after 截图与原型关键区域对照可复核，所有交互和鉴权测试保持通过。

## 门禁与 CI

- 新增设计 token 契约与关键视觉回归；`test:e2e` 继续在 CI build job 实际执行。
- `verify:web-style`、bundle、typecheck、lint、docs 和 flow 全绿。

## 非目标

- 不实现 Sessions 列表、问题详情、Agent 执行流图或自进化业务页面。
- 不引入暗色主题切换，不改变 Element Plus 的控件职责边界，不伪造领域数据。
