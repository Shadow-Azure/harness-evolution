# Contracts

前后端共享的类型与协议定义。

FastAPI OpenAPI 是唯一协议源。`openapi.json` 是确定性快照，`src/generated/api.d.ts` 由 `openapi-typescript` 生成；`fixtures/health.json` 来自真实 ASGI 响应，并同步生成 `src/generated/health-fixtures.ts`。这些产物都禁止手改。修改 API 后运行 `pnpm contract:generate`，`pnpm contract:check` 在 CI 中阻止漂移。

`src/index.ts` 只导出生成类型的稳定别名与少量跨端常量。尚未实现的功能不能提前写入生成契约。
