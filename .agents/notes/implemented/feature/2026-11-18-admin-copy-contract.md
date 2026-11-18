# Agent Note: 空间管理与鉴权文案对齐当前契约

Status: implemented

[English](2026-11-18-admin-copy-contract.en.md) | 中文

## Problem

空间管理页、V2 原型和设计文档对同一组权限与接口给出了不同说法：生产空间页只写“可以把任意用户加入空间”，弱化了全局管理员把自己设为空间管理员的权限；原型「鉴权接入」仍用 `email`、`he_session` 和 `204 Set-Cookie`，`design-v2.md` §3.3 也沿用同一旧契约；原型「上报接入」的请求体仍是 `bad_cases` 表的 `snake_case` 字段。实际 API 已经使用 `username` 登录、返回 `accessToken`/`expiresIn` 并写 `refresh_token` Cookie，上报也已统一 camelCase 且拒绝 body 里的 workspace 字段。文案漂移会让接入方照抄旧契约，也会让设计评审把实现误判为偏离。

## Decision

- 生产空间页与原型统一为“管理员可以把任意用户（包括自己）加入空间并任命为空间管理员”。
- 「鉴权接入」示例改为当前实现：`GET /api/auth/session` 返回 `PublicUser` + `SessionWorkspace` + `truncated`；`POST /api/auth/login` 接收 `username`/`password`、返回 `accessToken`/`expiresIn`/`user` 并写 HttpOnly、SameSite=Strict 的 `refresh_token` Cookie；补充 `refresh` 与 `logout`。
- 删除生产页“替换演示账号”的措辞；演示账号只保留在原型登录演示里，并明确不进入生产。
- 原型与 `design-v2.md` 的上报示例改为 camelCase `BadCaseIngest` 字段，保留 body 不接受 workspace、多带返回 `422` 的边界说明。
- 新增组件测试与真实浏览器 E2E。E2E 直接读取 `packages/contracts/openapi.json` 的 required 字段，校验页面契约与原型/设计文档包含所有必填字段，避免再次漂移。

## Alternatives considered

- **只改生产页面**：拒绝。原型和 `design-v2.md` 是接入方会读的第二、第三处事实源，留着旧字段仍会误导。
- **把页面文案抽成共享常量**：拒绝。原型是独立的静态 HTML，无法 import 生产常量；用 OpenAPI 驱动的测试锁定更可靠。
- **为旧 email / snake_case 示例保留 API 兼容**：拒绝。实际契约已经迁移，回退会扩大接口面并掩盖漂移。
- **在空间页增加账号选择或演示登录**：拒绝。生产不枚举账号，账号只能由管理员创建或通过 SSO 映射。

## Consequences

- 页面、原型与 `design-v2.md` 只在文案和示例上变化；登录、Cookie、RBAC 与上报写入逻辑不变。
- E2E 读取 OpenAPI required 字段，未来改 schema 未同步文案会直接失败。
- 文案证据由真实浏览器截图提供，基线为 m12-13 开发前的 `main`，不把截图提交进仓库。
