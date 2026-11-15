# Agent Note: 鉴权提供方接缝与回调占位

Status: implemented

[English](2026-11-15-auth-provider-seam.en.md) | 中文

## Problem

密码校验、用户查找和令牌签发原先都长在 `IdentityService` 里。要接 Cookie 或 SSO 时，登录路径、错误码和前端契约会被迫一起改；不接的时候又缺少一个能自动验证的回调错误契约。用户管理还允许管理员再建一个 `admin`，与“唯一全局管理员”的验收冲突。

## Decision

- `AuthProvider` 只暴露 `authenticate(Credentials) -> ProviderIdentity | None`；`PasswordProvider` 保留原有 argon2id 校验和 dummy 耗时抹平。`ProviderRegistry` 在启动时按 `HE_AUTH_PROVIDER` 选实现，`cookie` / `oidc` 属预留值，选中即抛 `AuthProviderConfigurationError`，不静默回退 password。
- `SessionBridge` 把已验证身份映射到已有用户：password 身份按内部 id，外部身份按唯一键 `(auth_provider, external_subject)`；映射不到返回 `403 AUTH_NO_MAPPING` 且不建号，停用账号返回 `403 FORBIDDEN`。映射成功后签发与密码登录相同的 access/refresh 对，业务和前端契约不变。
- `CallbackService` 用签名 nonce 加短时 state cookie（`HttpOnly`、`SameSite=Lax`、10 分钟）完成回调占位：未配置 provider `501 AUTH_PROVIDER_NOT_CONFIGURED`，state 缺失/过期/不匹配 `400 AUTH_STATE_INVALID`，code 缺失或被提供方拒绝 `401 AUTH_INVALID`，换取失败 `502 AUTH_PROVIDER_ERROR`，映射失败 `403`；成功 302 回 `HE_WEB_BASE_URL` 并设置 refresh cookie。回调公开并纳入登录限流；`state_challenge()` 留给未来的登录跳转端点。
- 配置新增 `HE_AUTH_PROVIDER`、预留的 `HE_SESSION_COOKIE_NAME` / `HE_SESSION_TTL_HOURS`，以及 `HE_OIDC_ISSUER` / `HE_OIDC_CLIENT_ID` / `HE_OIDC_CLIENT_SECRET_ENV`；secret 只存环境变量名。
- `IdentityService.create_user` 拒绝 `role=admin`（`422 ROLE_INVALID`），只有空库播种能创建全局管理员。

## Alternatives considered

- **在 `IdentityService.login` 里保留密码校验**：接新提供方就得改业务服务，接缝名存实亡；拒绝。
- **未知 provider 静默回退 password**：部署配置错误会被伪装成可用，违背 fail fast；拒绝。
- **按 IdP claims 自动建用户**：会绕过管理员审批并放大身份映射错误；拒绝。
- **把 state 放服务端存储**：当前单实例、无共享存储，签名 nonce + cookie 已能验证完整性与时效；拒绝额外存储。
- **本轮实现真实 OIDC 换取**：属于非目标，且需要网络与密钥环境；拒绝。

## Consequences

- 在实现 Cookie/OIDC provider 前，`/api/auth/callback` 始终返回 501；400/401/403/502 分支靠注入 provider 的测试守住。
- 会话桥只负责“外部身份到内部 token 对”；Cookie provider 的 opaque `he_session` 服务端存储仍未实现。
- state cookie 的写入方（登录跳转端点）尚未提供，接入方需先调用 `state_challenge()` 的服务端能力。
- 外部身份用户仍需管理员预置 `auth_provider` 与 `external_subject`；管理界面落地前没有专门入口。
- 唯一管理员由 service 层拦截，直接改库仍可绕过；需要更强约束时再评估数据库层方案。
