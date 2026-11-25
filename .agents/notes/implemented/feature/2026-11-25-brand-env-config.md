# Agent Note: 品牌名与副标题走 API 运行期配置

Status: implemented

[English](2026-11-25-brand-env-config.en.md) | 中文

## Problem

顶栏、登录页、强制改密卡与浏览器标题的品牌文案硬编码在 Web 源码里。生产 `.env` 由 systemd 注入 API，而前端产物在 CI 构建后同步到服务器，构建环境读不到服务器 `.env`；部署方换一个站点名只能改源码重新构建。

## Decision

API 在启动时把 `HE_BRAND_NAME` / `HE_BRAND_SUBTITLE` 读入 `Settings`，并把未设置、`None`、空串与纯空白统一归一为内置默认（`Harness Evolution` / 「轨迹诊断与自进化」），真实值去除首尾空白后使用。公开只读端点 `GET /api/app-config` 返回 `{"brand":{"name","subtitle"}}`，与 `/api/health` 一样无需登录，不写库、不写审计。Web 在 `bootstrapApp` 挂载前拉取一次并写入 Pinia `appConfig` store；加载最多等待 2 秒，超时后先挂载，请求继续在后台完成并更新响应式品牌。成功时覆盖品牌并写 `document.title`，失败或响应不合法时保留默认文案、照常挂载且永不抛错。顶栏、登录页与改密卡的品牌位读同一份 store，长品牌名用省略号截断。

## Alternatives considered

- 构建期 Vite env：拒绝，CI 构建读不到服务器 `.env`；同一份产物无法按部署配置品牌，等于把配置退回源码。
- nginx `sub_filter` / 模板注入：拒绝，需要按部署维护 HTML 替换规则，容易与前端产物、转义和 SPA 标题更新冲突，也无法覆盖登录页与改密卡的状态渲染。
- 运行期热更新：拒绝，需要监听文件或轮询配置，收益仅是一次部署级文案；重启 `harness-api` 已足够且可预期。
- 后台品牌设置页 / 按空间品牌：拒绝，超出本 issue 的交付边界，也引入新的持久化与权限面。

## Consequences

改 `.env` 后必须重启 `harness-api` 才生效。品牌默认值同时存在于 `apps/api/app/config.py`、`apps/web/src/api/appConfig.ts` 与 `apps/web/index.html` 的预加载标题，三处需同步维护；API/Web 单测分别锁定字面量，默认态 E2E 证明两侧一致。公开端点新增一个无需登录的只读面，但只暴露品牌文本，不含部署路径或凭据。首次加载失败时本次会话保持默认文案，刷新页面后重试；这是「挂载前拉取一次」的代价。长品牌名依赖 CSS 截断，顶栏在 640px 以下隐藏副标题与品牌文字、只保留标记，390px 视口由现有断点保证不横向溢出。
