# Agent Note: FastAPI 服务边界

Status: implemented

[English](2026-10-24-fastapi-service-boundary.en.md) | 中文

## Problem

现有 TypeScript/Fastify 壳只承载健康检查，却与目标 SaaS 的 Python 数据、任务与 OpenAPI 契约不一致。继续在旧壳上叠加会同时承担框架迁移与业务接入风险，也会让文档、CI 和本地命令继续指向即将删除的实现。

## Decision

- 后端改为 `apps/api` 下的 Python 3.12 + FastAPI 模块化单体，按 `api/service/db/third_party_api` 分层，路由只在 `main.py` 注册。
- 配置统一从 `HE_` 环境命名空间读取；健康检查保持公开并返回 `phase=scaffold`。
- API 文档与 OpenAPI 由 `HE_DOCS_ENABLED` 控制；开发默认开启，生产部署显式关闭。
- 所有可预期错误、未知路由、校验失败与未捕获异常输出 `{error:{code,message,details}}`；未捕获异常只暴露 request ID。
- 身份实现落地前，非公开 `/api/*` 路径由边界 middleware 返回 `401 AUTH_REQUIRED`，避免业务路由在无鉴权状态下意外开放。
- Python 依赖使用 `venv + pip`，仓库根提供 pnpm 包装命令；CI 使用 Python 3.12 执行 ruff、mypy、pytest 与覆盖率。
- 删除 `apps/server` Fastify 壳，避免双后端长期并存。

## Alternatives considered

- 在 Fastify 上继续叠加并在切换时一次性迁移：会让数据库与业务切片先依赖将被替换的框架，扩大回滚面；否。
- 直接引入数据库、鉴权和业务路由：m1-02 无法独立验收，且会把平台风险与业务缺陷混在同一 PR；否。
- 让非公开 API 暂时保持开放：身份尚未实现时会产生默认放行的安全债务；否。
- 把 Python 后端也纳入 pnpm workspace：pnpm 不管理 Python 依赖，会制造虚假的单一包管理边界；否。

## Consequences

- 本地与 CI 需要先建立 Python 3.12 venv；新增开发者命令由根 pnpm 包装保持统一入口。
- m1-06 必须替换临时鉴权边界，而不是在其后追加鉴权；否则健康检查之外仍会全部 401。
- 统一错误 envelope 成为前端拦截器与后续 OpenAPI 生成物的稳定输入。
- Web 壳暂留 React，直到 m1-05 单独切换 Vue；本轮只替换后端边界。
