# 统一空间管理权限与鉴权契约文案

[English](m12-13-admin-copy-contract.en.md) | 中文

```yaml flow
kind: issue
id: m12-13
milestone: m12
depends:
  - m7-03
  - m7-09
  - m12-02
priority: P2
status: done
scope:
  - apps/web/src/pages/workspaces/**
  - tests/e2e/m7-09-workspace-admin.test.mjs
  - tests/e2e/m12-13-admin-copy-contract.test.mjs
  - plans/**
  - docs/**
  - reports/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 340
  url: https://github.com/Shadow-Azure/harness-evolution/issues/340
```

## 背景

空间管理页面的信息架构在生产与原型之间已经基本一致，但仍有可直接修正的文案和契约示例差异：

- 原型明确说明管理员可以把任意用户“包括自己”加入空间并任命为空间管理员；生产表格说明只写“可以把任意用户加入空间”，弱化了全局管理员给自己授予空间管理员角色的能力。
- 原型「鉴权接入」仍用 `email` 作为登录字段并围绕演示账号替换；生产当前使用 `username`，登录响应包含 `accessToken`、`expiresIn` 与用户对象，页面正文也已说明 Cookie 会话现状。
- 原型「上报接入」仍展示旧 `bad_cases` snake_case 请求示例；生产对外契约已经使用 `badCaseId`、`sessionId`、`badCaseType` 等 camelCase 字段，并明确 body 不接受 `workspace`。

这些差异不需要改变认证或空间 API，只需要让页面说明、复制样例和原型设计文件与当前契约保持一致。

## 目标

- 在生产与原型空间管理页统一“包括自己”的权限说明。
- 让鉴权接入示例与当前用户名/Cookie 登录契约一致，并避免暗示生产存在演示账号选择。
- 让上报接入示例与当前 camelCase bad case 契约一致，保留 `workspace` 字段会返回 422 的说明。
- 增加文案快照/组件测试，防止设计稿、页面与 OpenAPI 再次漂移。
- 不改变接口请求、权限判定或凭据生成逻辑。

## 证据截图

**空间与额度**

| 生产环境 | V2 原型 |
| --- | --- |
| [![生产空间管理](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/prod-06-admin-spaces.jpeg)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/prod-06-admin-spaces.jpeg) | [![V2 原型空间管理](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/proto-06-admin-spaces.jpeg)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/proto-06-admin-spaces.jpeg) |

**鉴权接入**

| 生产环境 | V2 原型 |
| --- | --- |
| [![生产鉴权接入](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/prod-06d-admin-auth.jpeg)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/prod-06d-admin-auth.jpeg) | [![V2 原型鉴权接入](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/proto-06d-admin-auth.jpeg)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/proto-06d-admin-auth.jpeg) |

四图均为 `2816×1576` 的真实浏览器窗口截图。空间页文案差异见「包括自己」；鉴权页的结构一致，但登录字段和响应示例仍不同。

## 设计依据

- [08 §4.2 顶栏用户区、空间切换器与空间管理页](../../../plans/fullstack-design/08-frontend-implementation.md#42-顶栏用户区空间切换器与空间管理页v2)：空间管理页面结构与角色文案。
- [05 §4.16 工作空间、成员与凭据](../../../plans/fullstack-design/05-api-design.md#416-工作空间成员与凭据v2)：空间成员与凭据接口。
- [05 §4.17 空间 bad case 上报](../../../plans/fullstack-design/05-api-design.md#417-bad-case-上报v2凭据鉴权)：上报请求与鉴权边界。
- [05 §4.1 基础端点：健康检查与鉴权](../../../plans/fullstack-design/05-api-design.md#41-基础端点健康检查与鉴权)：登录/刷新/me 请求与响应。
- [V2 设计 §4.3 空间管理交互](../../../plans/ui-prototype-v2/design-v2.md#43-空间管理交互)：全局管理员把任意用户（包括自己）设为空间管理员。

## 实现内容

- 更新生产空间页说明为“管理员可以把任意用户（包括自己）加入空间并任命为空间管理员”，与原型及权限矩阵一致。
- 原型鉴权接入示例改用 `username` 登录，展示当前 `accessToken`/`expiresIn` 返回与 `GET /api/auth/session` 契约；删除会让读者误以为生产可选择演示账号的措辞。
- 原型和生产的 bad case 上报示例统一为当前 camelCase payload，并说明 `workspace` 字段由 URL/凭据决定，额外携带会返回 422。
- 更新 `plans/ui-prototype-v2/design-v2.md` 中与当前实现不一致的示例和说明；若生产页面文案已正确，只补测试锁定。
- 增加字符串/DOM 测试覆盖“包括自己”、登录字段、响应字段和 422 说明。

## 实施步骤

1. 盘点生产页面、原型 HTML 与 `design-v2.md` 中的权限、鉴权和上报示例差异。
2. 先添加文案断言测试，锁住当前 API 契约字段和权限说明。
3. 更新生产管理页与原型文案，不修改请求构造函数。
4. 更新设计文档示例，运行 `pnpm record:i18n`（若涉及常驻中英文文档）。
5. 运行 web、E2E、契约、文档和流程门禁，确认发送 payload 与展示示例一致。

## 依赖与交付边界

- 依赖：m7-03 提供认证契约，m7-09 提供空间管理页，m12-02 提供真实外部契约巡检；均已完成。
- 交付边界：只同步说明文字、示例和测试；不改变 API、Cookie、RBAC 或凭据生命周期。
- 原型中的演示账号只能作为旧设计痕迹被删除或标注，不得被解释为生产账号枚举能力。
- 若发现实际 API 与文档不一致，停止修改文案并在 PR 中报告，避免用文案掩盖契约漂移。

## 独立验证

```sh
pnpm test:web -- apps/web/src/pages/workspaces
pnpm test:e2e -- --pattern m12-13
pnpm contract:check
pnpm lint:docs
pnpm verify:flow
```

- 生产与原型都明确显示“包括自己”的空间管理员说明。
- 鉴权示例使用 `username` 并展示当前 access-token/session 契约。
- 上报示例使用 camelCase，页面明确 body 的 `workspace` 会触发 422。
- 页面渲染文字与 OpenAPI/真实类型一致，构建不产生契约漂移。

## 验收标准

- 空间管理、上报接入和鉴权接入三处的文案与当前实现一致。
- 原型设计文件不再使用旧 email/snake_case 示例误导实现。
- 文案测试锁定权限说明、登录字段、响应字段和 422 边界。
- 不改变任何请求 payload、认证 Cookie 或空间权限行为。
- 契约、web、E2E、文档和流程门禁全部通过。

## 门禁与 CI

- `pnpm test:web`、`pnpm test:e2e`、`pnpm contract:check`、`pnpm typecheck`、`pnpm lint:docs`、`pnpm verify:docs`、`pnpm verify:flow`。
- 涉及中英文常驻文档时运行 `pnpm record:i18n -- <pair>` 并提交配对记录。

## 非目标

- 不新增账号选择、账号枚举或演示登录能力。
- 不修改登录、刷新、注销、Cookie 或 SSO 实现。
- 不修改上报鉴权、凭据轮换、额度或 RBAC 行为。
- 不重构空间管理页面布局。
