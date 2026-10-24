# Database interface and SQLite/MySQL base

English | [中文](m1-03-database-base.md)

```yaml flow
kind: issue
id: m1-03
milestone: m1
depends:
  - m1-02
priority: P0
status: in-progress
scope:
  - AGENTS.md
  - apps/api/**
  - apps/api/alembic/**
  - apps/web/**
  - package.json
  - packages/contracts/**
  - plans/**
  - scripts/**
  - tests/integration/**
  - reports/**
  - .github/workflows/ci.yml
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 26
  url: https://github.com/Shadow-Azure/harness-evolution/issues/26
```

## Background





鉴权、轨迹和自进化都依赖同一个存储接缝；必须先确立跨方言规则，避免本地绿而 MySQL 红。

## Goals





- 实现 Database 抽象、SQLite/MySQL 适配器、事务、health 和 Alembic 基座。
- 建立跨方言 SQL 纪律和双方言 repository 测试基类。
- CI 添加 MySQL 8 service 并分离 sqlite/mysql 标记。

## Design authority





- [04 后端架构](../../../plans/fullstack-design/04-backend-architecture.md)

## Implementation





- SQLAlchemy async 引擎通过 Database 接口暴露，业务不直接创建 engine。
- 迁移使用双方言兼容类型；SQLite 变更走 batch 模式。
- health 报告 dialect 且失败有明确错误。

## Implementation steps





1. 先写连接、事务回滚、迁移升级和 health 的双方言失败测试。
2. 实现 Database、两个适配器、 Alembic env 和基线迁移。
3. 在 CI 配置 MySQL service 并运行 test:db:mysql。

## Dependencies and boundary





- 依赖：m1-02
- 交付边界：只交付连接/事务/迁移基座，不建领域业务表。

## Verification





```sh
pnpm test:db
pnpm test:db:mysql
```

- 空库 upgrade head 在双方言通过；事务异常零残留。
- MySQL service 在 CI 成功运行标记用例。
- 前后端单元测试与 Web→Vite→FastAPI 集成测试同步通过。

## Acceptance





- 同一 repository 测试类在两个 dialect 通过。
- `.env` 可选择 HE_DB_DIALECT 且无凭据入库。
- 数据库失败不会导致未处理崩溃。

## Gates and CI





- 双库 lane 从本 issue 起常驻 CI。
- 迁移脚本和数据库纪律有测试。
- 前后端覆盖率四项指标均不低于 80%，CI 必须实际执行对应命令。

## Non-goals

- No users, trace, bad-case, or evolution schema.
