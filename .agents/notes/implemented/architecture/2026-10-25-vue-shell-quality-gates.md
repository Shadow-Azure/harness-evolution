# Agent Note: Vue 壳与前端质量门禁

Status: implemented

[English](2026-10-25-vue-shell-quality-gates.en.md) | 中文

## Problem

React 开发壳没有路由化空视图、共享 query 数据层和 token 约束；前端质量主要靠测试与构建兜底，Vue Flow 可能进入首屏闭包，硬编码颜色也无法被机械拦截。

## Decision

- `apps/web` 使用 Vue 3、Vue Router、Pinia 和 TanStack Query 重建；`/sessions` 同步首屏，`/evolution` 路由懒加载并把 Vue Flow 隔离到 vendor chunk。
- 前端执行 ESLint、`vue-tsc`、Vitest jsdom、V8 四项 80% 覆盖率、MSW 测试服务、tokens 颜色扫描和 Vite manifest bundle 边界检查。
- 共享 HTTP 层把网络故障、拒绝状态与 malformed JSON 统一归一为 `ApiError`，health 的契约化 503 不误判为网络失败。
- CI 显式运行门禁自测试、前端 lint/type/test、tokens 与 bundle 守卫；跨栈集成继续验证真实 proxy、FastAPI 和共享契约。

## Alternatives considered

- 继续修补 React 壳：改动更小，但会偏离既定 Vue 生态和后续 Vue Flow 设计；否决。
- 只把 lint、bundle 和样式检查做成文档建议：容易绕过，也不能防止首屏回归；否决，改为 CI 实际执行。

## Consequences

- 前端改动必须通过 lint、类型、覆盖率测试、集成、token 与 bundle 门禁；首屏引入 Vue Flow 或硬编码颜色会失败。
- 新业务页面默认保持路由懒加载和共享 HTTP/query 层；领域页面继续按后续 issue 交付。
- MSW 只能留在测试依赖与测试代码中；运行时请求直接使用共享 HTTP 层。
