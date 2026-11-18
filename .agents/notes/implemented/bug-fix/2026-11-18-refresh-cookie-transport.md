# Agent Note: refresh Cookie 按请求协议决定 Secure

Status: implemented

[English](2026-11-18-refresh-cookie-transport.en.md) | 中文

## Problem

生产实例以 `HE_PRODUCTION=true` 跑在纯 HTTP 上，登录响应的 `refresh_token` 仍固定带 `Secure`。浏览器在非可信源（公网 IP 的 HTTP 页面）直接丢弃该 Cookie，导致整页刷新、新标签、地址栏进入和空闲 30 分钟后都没有 refresh 凭据可用；同页导航正常，排除了前端路由问题。

这不是“登录态设计错了”，而是 Cookie 的安全属性只看了部署阶段（`is_production`），没看浏览器实际使用的传输协议。生产先用 IP + HTTP 上线、域名与证书稍后补，是既有发布流程的真实状态；在 HTTPS 到位之前，固定 `Secure` 会让整套免登录机制完全失效。

## Decision

refresh Cookie 的 `Secure` 由请求协议决定：`request.url.scheme == "https"` 时为真，否则为假；新增可选 `HE_COOKIE_SECURE` 显式覆盖，空环境值按未设置处理。登录、刷新、IdP 回调清理和登出共用同一个判定函数，避免个别端点继续沿用 `is_production`。nginx 反代补 `X-Forwarded-Proto $scheme`，让 TLS 在代理终止时后端仍能识别 HTTPS；生产环境模板登记该开关。Cookie 的名称、`Path=/api/auth`、httpOnly、SameSite=Strict 与 14 天有效期保持不变。

## Alternatives considered

- **立即启用 HTTPS（域名 + 证书）**：长期正确，但要先有域名、DNS 和证书，会阻塞已经影响主路径的登录修复；作为 P0 部署动作继续由运维推进，不与本代码修复绑死。
- **无条件去掉 Secure**：改动最小，却会让未来 HTTPS 部署静默退化，属于用一个安全缺口换另一个；拒绝。
- **access token 持久化到 sessionStorage**：只能缓解刷新，救不了新标签、地址栏和 token 过期，还会扩大 XSS 可窃取的凭据面；拒绝。
- **去掉 bad case ID 的 `target=_blank`**：只是绕开症状，新标签与分享链接仍不可用；Cookie 修好后保持新窗口行为。

## Consequences

- HTTP 生产环境下 refresh token 会明文传输；这是 issue #348 明确接受的过渡风险，HTTPS 到位后应把 `HE_COOKIE_SECURE` 设回自动并验证 Secure 生效。
- TLS 在代理层终止时，必须传 `X-Forwarded-Proto` 或显式设置 `HE_COOKIE_SECURE=true`，否则后端会把请求当成 HTTP。
- 401 的交互提示、轮询退避和 sessionStorage 兜底仍属 P2，不在本次交付；启动恢复与单飞刷新链路不变。
- 新增开关对所有 Cookie 写入路径生效，后续若接入 OIDC，状态 Cookie 也要复用同一判定。
