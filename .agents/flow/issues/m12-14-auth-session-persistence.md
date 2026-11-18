# 生产 HTTP 登录态持久化：refresh Cookie 按协议决定 Secure

[English](m12-14-auth-session-persistence.en.md) | 中文

```yaml flow
kind: issue
id: m12-14
milestone: m12
depends:
  - m7-03
priority: P2
status: in-progress
scope:
  - apps/api/app/api/auth.py
  - apps/api/app/config.py
  - apps/api/tests/identity/**
  - deploy/**
  - docs/**
  - tests/e2e/**
  - plans/**
  - reports/**
  - .agents/flow/**
  - .agents/notes/**
adr:
  - ../../notes/implemented/bug-fix/2026-11-18-refresh-cookie-transport.md
github:
  number: 348
  url: https://github.com/Shadow-Azure/harness-evolution/issues/348
```

## 背景

生产实例以 `HE_PRODUCTION=true` 运行在纯 HTTP 上（先用公网 IP 访问，nginx 只监听 80）。`set_refresh_cookie` 把 `secure` 固定为 `settings.is_production`，于是登录响应下发 `Secure` 的 `refresh_token`；浏览器在非可信源（公网 IP 的 HTTP 页面）丢弃该 Cookie。整页加载、新标签、地址栏进入和空闲约 30 分钟后，前端启动或 401 单飞刷新都拿不到 refresh Cookie，只能跳回登录页；同页导航不受影响，因此不是前端路由问题。生产证据、时间线与验收场景见 issue #348。

## 目标

- 生产 HTTP 部署下登录响应下发浏览器可保存的 refresh Cookie，刷新、新标签、地址栏进入和空闲 token 过期后保持登录。
- HTTPS 直连或 TLS 在反向代理终止时仍下发 `Secure` Cookie，不降低 HTTPS 部署的安全性。
- 主动退出登录继续清 Cookie 并跳登录页。
- 保持 refresh Cookie 既有的 httpOnly、SameSite=Strict、Path=/api/auth 与 14 天有效期。

## 设计依据

- [plans/fullstack-design/05-api-design.md §鉴权端点](../../../plans/fullstack-design/05-api-design.md)：refresh Cookie 的 httpOnly + SameSite=Strict + 14 天契约，登录/刷新/登出端点行为。
- [plans/fullstack-design/08-frontend-implementation.md §HTTP 传输层](../../../plans/fullstack-design/08-frontend-implementation.md)：启动恢复与 401 单飞刷新；本次不改变该链路。
- [docs/architecture.md](../../../docs/architecture.md)：鉴权与错误共用边界。

## 实现内容

- `Settings.cookie_secure` 增加可选布尔开关（`HE_COOKIE_SECURE`），留空表示按请求协议自动；空字符串按未设置处理。
- `app/api/auth.py` 统一用 `refresh_cookie_secure(request)` 计算标记：显式开关优先，否则仅当 `request.url.scheme == "https"` 时为真；登录、刷新、IdP 回调清理与登出共用同一判定。
- nginx 反代补 `X-Forwarded-Proto $scheme`，让 HTTPS 终止后的后端能识别真实协议；生产环境模板登记 `HE_COOKIE_SECURE`。
- 单元测试覆盖 HTTP 生产、HTTPS、显式开关与空环境值四条路径。
- 生产构建 + HTTP 浏览器冒烟覆盖刷新、新标签、地址栏、空闲过期与退出。

## 实施步骤

1. 在配置层加入可选的 Cookie Secure 开关并规范化空环境值。
2. 在鉴权 HTTP 适配层用请求协议计算 Secure，替换所有固定 `is_production` 判定。
3. 更新 nginx 反代头与生产环境模板说明。
4. 补齐 API 单测，运行 lint/typecheck/test 与浏览器冒烟。

## 依赖与交付边界

- 依赖：m7-03 的 refresh Cookie 与启动恢复链路。
- 交付边界：只决定 Cookie 的 Secure 属性；Cookie 名称、路径、有效期、SameSite 与 httpOnly 不变。
- 不改变 bad case 新窗口打开行为；Cookie 修复后新标签自然保持登录。
- GitHub #348 保留生产证据原文；本文件是实施契约，`pnpm flow:sync` 前需人工合并正文，避免覆盖截图与时间线。
- 同一 PR 合并最新 main 并把已关闭的 m12-09 / m12-13 本地状态对齐为 done，解除 `flow-online` 对所有 PR 的阻塞。

## 独立验证

```sh
pnpm test:api -- tests/identity/test_auth.py
pnpm lint:api
pnpm typecheck:api
```

- HTTP 生产配置的登录响应不含 `Secure`，`POST /api/auth/refresh` 返回 200。
- HTTPS 请求的登录响应含 `Secure`；显式 `HE_COOKIE_SECURE=true` 在 HTTP 下也含 `Secure`。
- 生产构建浏览器冒烟：刷新、新标签、地址栏进入、空闲过期后仍在工作空间，退出后回到 `/login`。

## 验收标准

- 生产 HTTP 下浏览器 Cookie 存储中存在 `refresh_token`，刷新/新标签/地址栏/空闲 30 分钟均保持登录。
- 主动退出登录仍跳 `/login` 且清除 refresh Cookie。
- HTTPS 部署的 `Secure` 标记不退化；代理终止 TLS 时可用 `HE_COOKIE_SECURE` 显式开启。
- 总览、Session、自进化与空间管理回归不出现新的 401 循环。
- 相关 API 测试、lint、typecheck、e2e 与 CI 全绿。

## 门禁与 CI

- `pnpm test:api`、`pnpm lint:api`、`pnpm typecheck:api`。
- `pnpm test:e2e` 与跨栈集成测试。
- `pnpm verify:flow --diff origin/main`、`pnpm verify:docs`、`pnpm contract:check`。

## 非目标

- 不采购域名、证书或在代码仓库内启用 HTTPS；P0 的 HTTPS 部署仍由运维按现有发布流程推进。
- 不实现 401 交互提示、轮询退避或 access token 写入 sessionStorage 的 P2 兜底。
- 不改变 bad case ID 新窗口链接与详情页信息架构。
