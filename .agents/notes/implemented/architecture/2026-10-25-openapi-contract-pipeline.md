# Agent Note: OpenAPI 契约生成与防漂移

Status: implemented

[English](2026-10-25-openapi-contract-pipeline.en.md) | 中文

## Problem

前端的健康与错误类型若继续手写，会与 FastAPI 重复表达同一字段。后端新增枚举、改大小写或调整 503 schema 时，TypeScript 编译器看不出漂移，前端只能在运行期发现契约不一致。

## Decision

- FastAPI OpenAPI 是接口契约唯一事实源；导出时递归排序对象 key 并固定 JSON 缩进，版本库保存确定性快照。
- `openapi-typescript` 从快照生成 `packages/contracts/src/generated/api.d.ts`，文件带 `@generated` 标记；`src/index.ts` 只导出稳定别名和跨端常量。
- `contract:generate` 更新快照与生成物；`contract:check` 在临时目录重算并逐字比较，不修改工作树，缺失、手改或后端漂移都会失败并提示重生成命令。
- CI 在构建前执行 `contract:check`；路由门禁把 API、共享契约和 Web 改动导向同一检查。

## Alternatives considered

- 继续手写前端接口类型：字段少时成本低，但会形成第二事实源，必须在每次 API 改动中人工同步；否决。
- 运行时从 `/api/openapi.json` 动态读取类型：TypeScript 在构建期无法获得类型，生产运行时还依赖文档端点开放；否决。
- 只在 CI 重新生成后执行 `git diff`：实现可行，但会污染工作树，且不利于区分快照与生成物错误；改为临时目录逐文件比较。

## Consequences

- API 改动后必须运行 `pnpm contract:generate`；忘记重生成会被 `contract:check` 在本地和 CI 同时拦截。
- 生成文件不可手改，修复契约应改 FastAPI DTO 或生成脚本。
- 尚未实现的接口不会提前进入契约；原型专用会话类型暂留，直到对应 API 切片的 issue 再替换。
