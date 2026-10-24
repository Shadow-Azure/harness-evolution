# m2-01 Synthetic Fixtures

English | [中文](m2-01-synthetic-fixtures.md)

```yaml flow
kind: issue
id: m2-01
milestone: m2
depends:
depends: []
priority: P0
status: backlog
scope:
  - fixtures/**
  - apps/api/**
  - scripts/**
  - package.json
  - .github/workflows/ci.yml
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr:
adr: []
github:
  number: 33
  url: https://github.com/Shadow-Azure/harness-evolution/issues/33
```

## Background





m2-01 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## Goals





- 完成 m2-01 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## Design authority





- [01 §5.3 演示数据边界](../../../plans/fullstack-design/01-architecture.md)
- [04 §5.3 fixtures 唯一形态](../../../plans/fullstack-design/04-backend-architecture.md)
- [06 §3 轨迹侧表](../../../plans/fullstack-design/06-database-design.md)

## Implementation





- 定义 payload/session/agent/bad_case/evolution 最小合成 schema
- 实现 fixtures seed CLI 与 fixture manifest
- 为 schema、幂等 seed、未知字段和大字段写校验

## Implementation steps





1. 先写空库可 seed 和重复 seed 零新增的失败测试
2. 实现 fixture 模型与 loader
3. 接入 verify:fixtures
4. 更新 README 与 Agent Note

## Dependencies and boundary





- 依赖：无
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:api -- tests/m2-01-synthetic-fixtures
pnpm test:db
```

- fixture:check 与 seed 测试通过
- CI 无 claude-code-sessions 也能得到确定性数据

## Acceptance





- fixtures schema 稳定且大小受控
- seed 幂等
- 未知字段拒绝

## Gates and CI





- fixture schema gate、数据卫生 gate、CI seed 冒烟

## Non-goals

- 不提交真实轨迹
- 不实现 UI
