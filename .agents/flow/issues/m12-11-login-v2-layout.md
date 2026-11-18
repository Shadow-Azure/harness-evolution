# 登录页对齐 V2 原型的信息架构

[English](m12-11-login-v2-layout.en.md) | 中文

```yaml flow
kind: issue
id: m12-11
milestone: m12
depends:
  - m7-03
priority: P2
status: backlog
scope:
  - apps/web/src/pages/login/**
  - apps/web/src/styles/**
  - tests/e2e/m1-shell.test.mjs
  - tests/e2e/m12-11-login-v2-layout.test.mjs
  - plans/**
  - docs/**
  - reports/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 338
  url: https://github.com/Shadow-Azure/harness-evolution/issues/338
```

## 背景

生产登录页是约 420px 宽的单列白卡，只包含品牌小块、登录标题、用户名/密码与页脚说明，页面大部分区域留白。

V2 原型使用约 920px 的双栏卡片：左侧解释工作空间隔离、归因进入自进化流程和默认 10 个 Session，右侧承载登录表单与账号说明。原型中的四个账号按钮是打桩演示，不应原样出现在生产，否则会泄露或枚举真实账号；需要对齐的是信息层级和视觉结构，而不是演示数据。

现有生产权限模型仍只有一个全局管理员、管理员创建用户、首次登录强制改密；登录控件是用户名而不是邮箱。因此本 issue 必须同时保留安全边界与现有认证语义。

## 目标

- 将生产登录页调整为 V2 的双栏信息架构，窄屏回落为单列。
- 左栏展示产品能力与工作空间/归因/默认 Session 说明，不展示具体用户、邮箱或可枚举账号。
- 右栏保留用户名、密码、内联错误、加载态和首次改密提示，复用现有登录状态机。
- 统一品牌标记、圆角、边框、间距和响应式断点，与主应用共享现有 token。
- 补齐键盘顺序、焦点可见、错误播报和 390px 窄屏回归。

## 证据截图

| 生产环境 | V2 原型 |
| --- | --- |
| [![生产登录页](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/prod-07-login.jpeg)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/prod-07-login.jpeg) | [![V2 原型登录页](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/proto-07-login.jpeg)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/proto-07-login.jpeg) |

两图均为 `2816×1576` 的真实浏览器窗口截图。生产为单列小卡；原型为左侧能力说明和右侧表单的双栏卡片。原型账号列表只是演示，不作为生产需求。

## 设计依据

- [08 §4.1 登录页与强制改密](../../../plans/fullstack-design/08-frontend-implementation.md#41-登录页与强制改密)：用户名/密码、错误、强制改密与回跳语义。
- [08 §12 样式与视觉实现](../../../plans/fullstack-design/08-frontend-implementation.md#12-样式与视觉实现)：设计 token 与 Element Plus 分工。
- [08 §13 三态、错误与加载](../../../plans/fullstack-design/08-frontend-implementation.md#13-三态错误与加载)：登录请求的状态展示。
- [V2 设计 §2.2 新增但仍使用 V1 语言](../../../plans/ui-prototype-v2/design-v2.md#22-v2-新增但仍使用-v1-语言)：登录页视觉基线。
- [V2 设计 §3 身份与权限](../../../plans/ui-prototype-v2/design-v2.md#3-身份与权限)：唯一全局管理员、无公开注册和成员角色约束。

## 实现内容

- `pages/login/Index.vue` 改为桌面双栏：左栏品牌/能力说明，右栏登录表单；不使用原型的四账号列表。
- 左栏文案围绕工作空间隔离、对象级归因和最新 10 个 Session；不读取用户列表，不提供账号枚举或选择。
- 登录表单继续使用 `LoginForm.vue` 的用户名/密码与 `useLogin`，保留错误、禁用/加载状态和自动补全属性。
- 卡片宽度、留白、圆角和背景复用现有 token；390px 时改为单列，左栏压缩为品牌与简短能力摘要。
- 增加 `data-testid` 与可访问区域标题；按 Tab 顺序从能力说明进入用户名、密码、登录按钮。
- 组件测试覆盖普通登录、错误、加载和首次改密入口；E2E 覆盖桌面/窄屏布局与登录回跳。

## 实施步骤

1. 先补双栏结构、无账号枚举和窄屏无溢出的失败测试。
2. 重构登录页模板与 scoped style，不改 `LoginForm` 请求逻辑。
3. 将能力说明从演示数据改成静态产品事实，移动端隐藏低价值长说明。
4. 校准焦点、aria 和 Tab 顺序，验证错误提示仍为内联 `role=alert`。
5. 更新登录页视觉/交互测试与生产构建截图。
6. 更新前端实现文档并补 Agent Note，运行 web、E2E、类型和文档门禁。

## 依赖与交付边界

- 依赖：m7-03 提供现有 Cookie/用户名登录与会话恢复语义，已完成。
- 交付边界：只改登录页展示与响应式布局；不改登录 API、Cookie、强制改密、权限或路由守卫。
- 原型账号列表仅作为视觉参考，不得进入生产 DOM 或 API 请求。
- 本 issue 不接入 SSO/OIDC；接入要求仍在空间管理鉴权页说明。

## 独立验证

```sh
pnpm test:web -- apps/web/src/pages/login
pnpm test:e2e -- --pattern m12-11
pnpm typecheck:web
pnpm verify:web-style
pnpm verify:bundle
```

- 1440px 下为双栏卡片，390px 下为单列且无横向溢出。
- 页面不显示用户列表、邮箱列表或账号选择按钮。
- 用户名、密码、错误、加载和登录按钮的键盘顺序与 aria 状态正确。
- 登录成功、错误密码和首次改密回跳行为与现有实现一致。
- 视觉 token 门禁与首屏 bundle 边界通过。

## 验收标准

- 生产登录页具备 V2 双栏信息层级，且不暴露账号枚举数据。
- 现有用户名/密码登录、错误提示、加载态和首次改密路径不回归。
- 桌面与 390px 窄屏在视觉和可访问性上通过截图与 DOM 断言。
- 所有颜色/间距使用现有设计 token，不引入第二套视觉变量。
- 新测试与文档通过 CI。

## 门禁与 CI

- `pnpm test:web`、`pnpm test:e2e`、`pnpm typecheck:web`、`pnpm verify:web-style`、`pnpm verify:bundle`、`pnpm lint:docs`、`pnpm verify:flow`。
- PR 附桌面与窄屏截图，并断言账号列表文本/DOM 不存在。

## 非目标

- 不在生产复制原型演示账号、邮箱或一键切换用户功能。
- 不改变唯一全局管理员、用户创建或首次改密规则。
- 不实现 SSO/OIDC 回调或公开注册。
- 不重做主应用顶栏与其他业务页面。
