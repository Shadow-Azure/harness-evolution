# Agent Note: 空间管理四 Tab 与一次性凭据

Status: implemented

[English](2026-11-15-workspace-admin-ui.en.md) | 中文

## Problem

m7-05 已经提供空间创建与额度、成员角色、空间管理员自任、上报凭据的完整 API，m7-08 又把所有业务页收进 `/workspaces/:wid` 壳，但管理能力仍停留在 `/api`：全局管理员要创建空间、空间管理员要调整额度或轮换凭据，只能手工调用接口。凭据尤其危险——列表接口永不回显明文，如果前端把创建响应留在组件状态里，一次误刷新就可能把明文带进缓存或日志。界面还必须把“服务端权限”与“前端隐藏入口”分开：隐藏按钮只是体验，真正的 403/404 仍由 API 返回。

## Decision

- 新增 `/workspaces/:wid/admin` 路由与 `pages/workspaces/Admin.vue`，四个 Tab 对齐原型：`spaces`（空间与额度）、`members`（成员与角色）、`ingest`（上报接入）、`auth`（鉴权接入）。Tab 存于 `?tab=`，可直接深链。
- 入口按有效角色显示：顶栏 `#tn-admin` 与空间切换器底部「空间设置 →」只对 `space_admin` / `global_admin` 出现；成员与只读仍可进入页面，但顶部显示「只读」badge，所有写按钮隐藏，凭证 Tab 只渲染说明卡不请求凭据接口。空间管理员看到的 `space_admin` 行禁用为只读 badge，不能改角色或移除。
- 全局管理员在 `spaces` Tab 看到全部空间表与「创建工作空间」；空间管理员只看到当前空间的额度、管理员与「调整额度 / 管理成员」。创建弹窗的初始空间管理员默认勾选当前账号，候选来自 `GET /api/users`（仅全局管理员、仅创建弹窗使用，不另建用户目录页）。
- 凭据创建响应只写入组件内的 `createdCredential`，弹窗关闭时置空并从 DOM 移除；curl 示例在明文不可读时显示 `<workspace credential>` 占位。轮换先创建新凭据、展示一次明文，再让用户按需撤销旧凭据，避免中断上游。
- 缓存键补 `["ws", wid, "admin", "members" | "member-candidates" | "credentials"]`；成员/空间写操作失效 admin 前缀、`["ws"]` 与 `["auth","session"]`，凭据轮换只失效 credentials。所有请求继续走 `api/http.ts` 的 Bearer 与 401 刷新。
- 契约只补 `UserListResponse` 导出；管理接口类型全部复用 `@harness/contracts` 的生成类型，避免前后端字段漂移。

## Alternatives considered

- **在 `spaces` Tab 内联创建表单**：弹窗关闭即清理明文/表单状态的路径更清晰，且与原型 `WorkspaceFormDialog` 一致；拒绝。
- **让成员/只读也请求凭据接口，只隐藏按钮**：会拿到 403 并污染全局错误提示；按角色关闭查询，页面只渲染只读说明。
- **创建空间时手填用户 ID**：易错且需要全局用户目录；使用仅管理员可读的 `GET /api/users` 只为初始管理员选择，不新增目录页。
- **把凭据明文放进 Pinia 或 query cache**：会被 devtools、持久化和缓存失效逻辑意外带走；只用组件局部 `ref`，关闭即丢。
- **由前端根据角色决定是否允许写**：服务端仍是唯一权威；前端只做入口可见性，直接调用 API 的 403/404 由 m7-05 的测试覆盖。

## Consequences

- 管理页新增两条请求链（`GET /api/workspaces` 与 `GET /api/users`），全局管理员首次进入会多一次用户列表读取；空间管理员不请求用户列表。
- 成员与只读可以进入管理页查看当前空间信息，但 `ingest` Tab 不请求凭据，避免成员看到可复制的接口地址以外的敏感状态。
- 凭据明文只在创建成功的弹窗内存在；若用户没复制就关闭，只能重新轮换，符合“仅展示一次”的安全边界。
- 空间创建弹窗依赖 `GET /api/users` 返回全部账号；账号规模很大时该端点没有分页，后续需要服务端搜索或分页。
- 前端隐藏入口不能替代服务端校验；m7-05 的角色矩阵仍是验收基线，任何新写入口都必须同时有 API 403 测试。
- 管理弹窗依赖 `unplugin-vue-components` 的按需样式注入；显式 import Element Plus 组件会绕过 style side effect，导致对话框按静态布局铺满页面。新增弹窗沿用全局组件写法（不在脚本里手写 `ElDialog` / `ElForm` import）。
