# FastAPI 骨架与统一错误模型

[English](m1-02-api-scaffold.en.md) | 中文

```yaml flow
kind: issue
id: m1-02
milestone: m1
depends: []
priority: P0
status: in-progress
scope:
  - apps/api/**
  - apps/server/**
  - apps/web/**
  - .gitignore
  - packages/contracts/**
  - package.json
  - pnpm-workspace.yaml
  - pnpm-lock.yaml
  - pyproject.toml
  - scripts/**
  - .github/workflows/ci.yml
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
  - AGENTS.md
  - README.md
  - README.en.md
  - README.i18n.yaml
adr: []
github:
  number: 25
  url: https://github.com/Shadow-Azure/harness-evolution/issues/25
```

## 背景

当前 Fastify 壳与目标 SaaS 后端不一致，必须先建立可测试的 FastAPI 边界，再叠加数据与业务。

## 目标

- 创建 apps/api 的 FastAPI 3.12 模块化骨架。
- 实现 pydantic-settings 配置、统一错误模型和 /api/health。
- 接入 ruff、mypy、pytest、coverage 与 CI Python 环境。

## 设计依据

- [04 后端架构](../../../plans/fullstack-design/04-backend-architecture.md)

## 实现内容

- 按 api/service/db/third_party_api 分层创建目录，HTTP 层不做业务。
- 用 exception handler 输出 {error:{code,message,details}}。
- 移除 apps/server Fastify 实现并调整 pnpm 脚本。

## 实施步骤

1. 先写 health、鉴权未接入 401、未知路由和错误模型的失败 pytest。
2. 创建 config、app、routes 和错误模型实现。
3. 建立 venv/pip 安装脚本和根 pnpm 包装命令。
4. 删除旧 server 并更新 docs/architecture 与 Agent Note。

## 依赖与交付边界

- 依赖：无
- 交付边界：只交付无数据库、无业务状态的后端骨架；旧 health 契约允许 phase=scaffold。

## 独立验证

```sh
pnpm test:api
pnpm lint:api
pnpm typecheck:api
```

- health 返回 ok/service/phase；错误路径返回统一 error 对象。
- ruff/mypy 无 warning；pytest 覆盖全部新增路由。

## 验收标准

- `pnpm dev:api` 可启动且 /api/health 可访问。
- Fastify 实现不再存在于仓库。
- CI 静态 lane 执行 Python lint/type/test。

## 门禁与 CI

- Python lint/type/test 进入 CI。
- pnpm route:gates 对 apps/api 改动推荐后端命令。

## 非目标

- 不接数据库、鉴权、轨迹或 AI。
