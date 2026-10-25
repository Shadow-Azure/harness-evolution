# m2-01 synthetic fixtures

[English](m2-01-synthetic-fixtures.en.md) | 中文

```yaml flow
kind: issue
id: m2-01
milestone: m2
depends: []
priority: P0
status: in-progress
scope:
  - AGENTS.md
  - fixtures/**
  - apps/api/**
  - scripts/**
  - package.json
  - .github/workflows/ci.yml
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
  - plans/**
  - reports/**
adr: []
github:
  number: 33
  url: https://github.com/Shadow-Azure/harness-evolution/issues/33
```

## 背景

m2-01 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## 目标

- 完成 m2-01 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## 设计依据

- [01 §5.3 演示数据边界](../../../plans/fullstack-design/01-architecture.md)
- [04 §5.3 fixtures 唯一形态](../../../plans/fullstack-design/04-backend-architecture.md)
- [06 §3 轨迹侧表](../../../plans/fullstack-design/06-database-design.md)

## 实现内容

- 定义 payload/session/agent/bad_case/evolution 最小合成 schema
- 实现 fixtures seed CLI 与 fixture manifest
- 为 schema、幂等 seed、未知字段和大字段写校验

## 实施步骤

1. 先写空库可 seed 和重复 seed 零新增的失败测试
2. 实现 fixture 模型与 loader
3. 接入 verify:fixtures
4. 更新 README 与 Agent Note

## 依赖与交付边界

- 依赖：无
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## 独立验证

```sh
pnpm test:api -- tests/m2-01-synthetic-fixtures
pnpm test:db
pnpm fixtures:check
pnpm fixtures:seed
```

- fixture:check 与 seed 测试通过
- CI 无 claude-code-sessions 也能得到确定性数据

## 验收标准

- fixtures schema 稳定且大小受控
- seed 幂等
- 未知字段拒绝

## 门禁与 CI

- fixture schema gate、数据卫生 gate、CI seed 冒烟

## 非目标

- 不提交真实轨迹
- 不实现 UI
