# Agent Note: 前端身份状态与恢复

Status: implemented

[English](2026-10-25-identity-frontend.en.md) | 中文

## Problem

refresh 凭据只能在 httpOnly cookie 中，access token 又不能落持久存储；同时路由守卫、HTTP 401 与强制改密都可能发现身份状态变化。若这些路径各自读 cookie 或直接互相 import，就会出现首屏闪登录、并发 refresh 重放、循环依赖和错误页残留。

## Decision

- Pinia 只在内存保存 access token 与当前用户；应用启动先尝试 refresh 与 `/me`，再等待 router ready 和挂载。路由守卫在未完成恢复时复用同一个启动 Promise。
- `api/http.ts` 只通过注入的 access-token、refresh、过期和强制改密回调接触身份；只有 login/refresh 是无需恢复的公开端点，并发 401 共享一个 refresh Promise，并保留原请求方法与 body 各重放一次。`AUTH_INVALID` 始终保留表单语义，不刷新也不触发会话过期；换 token 后仍失败的受保护请求统一清态回登录。
- 登录与改密回跳只接受应用相对路径；改密成功严格按 `change-password → refresh → me → redirect` 执行，确保新 token 的强制改密声明已更新。
- Element Plus 的输入与按钮由类型化按需解析器自动导入，同时加载 base/组件样式；Element Plus 排除在 Vite 依赖预构建外，避免首次使用触发整页重载。顶栏按 1100px/640px 断点收缩品牌文字与用户摘要；退出由 mutation 调后端，但无论请求成败都清内存态和 query cache。

## Alternatives considered

- 在 HTTP 层直接 import store/router：少一层注册，但形成传输层与装配层循环依赖，测试也无法替换恢复路径；否决。
- access token 写入 localStorage：刷新页面更快，但违背短命 token 只留内存的安全边界；否决。
- 并发 401 各自 refresh：实现简单，却会重复旋转 refresh cookie 并让其中一个请求重放失败；否决。

## Consequences

- 页面首次导航可能等待一次 `/api/auth/refresh`；无有效 cookie 时以 `AUTH_EXPIRED` 快速进入登录页，改密后的显式 refresh 失败也走同一恢复边界。
- 所有受保护业务请求共享传输层语义；新增域 API 不得自行处理 401 或读取 refresh cookie。
- 未实现用户管理、注册、OAuth 与记住密码；这些能力需要新的契约和决策，不能复用当前前端状态模型。
