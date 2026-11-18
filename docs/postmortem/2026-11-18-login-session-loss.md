# 生产登录态丢失：refresh Cookie 被浏览器丢弃

[English](2026-11-18-login-session-loss.en.md) | 中文

## 影响

生产所有用户受影响。用公网 IP + HTTP 访问时，登录后整页刷新、新开标签、地址栏直接进入和空闲约 30 分钟都会回到登录页；同页导航、空间切换、总览筛选与 Session 搜索保持正常。没有数据丢失，影响是反复重新登录，以及「点击 bad case ID 在新窗口打开错误详情」这条主路径每次都要重新认证。主动退出登录后跳登录页属于预期，不计入本次事故。

## 时间线

以下时间为 2026-11-18 CST。

- 10:05 开始生产前端冒烟，覆盖总览、Session 错误查看、自进化与空间管理。
- 10:10:02 登录。10:10–10:40 同页导航、工作空间切换、总览筛选/分页、Session 筛选/搜索均正常；`/api/acquisition/status` 约每 15 秒轮询一次，共 121 次。
- 10:40:14 该轮询返回 401，随后的 refresh 也返回 401；10:40:15 页面自动跳 `/login`，全程 30 分 13 秒且无用户操作。
- 10:45 冒烟结束。浏览器 Cookie 存储为空，`localStorage`/`sessionStorage` 为空，HTTPS 访问连接超时。
- 10:59 创建 issue #348 正式跟踪（此前误提交到 Shadow-Azure/ai-eval-platform#280）。
- 12:10 用生产构建 + HTTP + 非 loopback 地址复现：登录成功但 Cookie 存储无 `refresh_token`，刷新落回登录页。
- 12:12 修复后同一脚本通过：刷新、新标签、地址栏、空闲过期均保持登录，主动退出仍回登录页。

## 根因

直接触发：登录响应的 refresh Cookie 把 `Secure` 固定绑定到 `settings.is_production`。生产以纯 HTTP 部署，浏览器在非可信源丢弃 `Secure` Cookie，前端启动和 401 单飞刷新都拿不到 refresh 凭据。

系统性条件：

- Cookie 安全属性只看部署阶段，不看浏览器实际使用的传输协议；「先用 IP + HTTP 上线、域名与证书稍后补」又是既有发布流程的常规状态。
- 发布流程没有为「HTTPS 尚未就绪」提供显式开关，也没有在生产冒烟里检查 Cookie 是否真的落盘。
- E2E 跑在 `127.0.0.1`；Chrome 把 loopback 当作可信源，会接受 HTTP 上的 `Secure` Cookie，因此既有测试无法暴露该缺陷。
- `secure` 判定散落在登录、刷新、回调与登出四处，缺少单一来源。

## 处置

- 代码修复：refresh Cookie 的 `Secure` 改为按请求协议决定（HTTPS 才加），新增可选 `HE_COOKIE_SECURE` 显式覆盖；登录、刷新、回调清理与登出共用同一判定。
- 部署配套：nginx 反代补 `X-Forwarded-Proto $scheme`，生产环境模板登记 `HE_COOKIE_SECURE`。
- 验证：API 单测覆盖 HTTP 生产、HTTPS、显式开关与空环境值；生产构建 + HTTP + 非 loopback 地址的浏览器冒烟覆盖刷新、新标签、地址栏、空闲过期与主动退出。
- 上线：合并后沿用既有 Deploy workflow；HTTPS 启用仍作为独立 P0 运维动作推进。

## 防复发

- 生产模板与 nginx 配置固化 `HE_COOKIE_SECURE` 与 `X-Forwarded-Proto`，避免 TLS 终止后 Secure 静默退化（本 PR）。
- 浏览器冒烟使用非 loopback 的 HTTP 源，绕开 Chrome 对 `localhost` 的可信例外；截图与场景矩阵随 PR 交付（本 PR）。
- HTTPS 上线后必须用同一冒烟确认 Cookie 带 `Secure`，并回归刷新、新标签与空闲过期。
- 归属 issue #348 / flow issue `m12-14`；后续若接入 OIDC，状态 Cookie 必须复用同一判定。
