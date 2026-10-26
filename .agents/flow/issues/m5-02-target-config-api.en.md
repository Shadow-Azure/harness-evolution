# m5-02 Target Config Api

English | [中文](m5-02-target-config-api.md)

```yaml flow
kind: issue
id: m5-02
milestone: m5
depends:
  - m5-01
priority: P0
status: done
scope:
  - apps/api/**
  - packages/contracts/**
  - fixtures/**
  - plans/**
  - reports/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 51
  url: https://github.com/Shadow-Azure/harness-evolution/issues/51
```

## Background





m5-02 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## Goals





- 完成 m5-02 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## Design authority





- [05 §4.11 对象配置](../../../plans/fullstack-design/05-api-design.md)
- [06 §5.1 targets](../../../plans/fullstack-design/06-database-design.md)
- [07 §5.2](../../../plans/fullstack-design/07-backend-implementation.md)

## Implementation





- 实现 evolution_targets CRUD、启用过滤、repoUrl/defaultRef/subDir 校验和被引用删除 409
- 聚合 agents.model 清单

## Implementation steps





1. 写校验、启用、引用冲突和清单失败测试
2. 实现 service/routes
3. 生成契约

## Dependencies and boundary





- 依赖：m5-01
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:api -- tests/m5-02-target-config-api
pnpm test:db
pnpm contract:check
```

- API 测试通过
- 配置错误返回明确 422/409
- 模型清单来自真实 agents

## Acceptance





- 只有启用对象可被向导使用

## Gates and CI





- route gate、contract gate、双方言测试

## Non-goals

- No scope creep beyond the listed non-goals and acceptance.
