# m2-04 Agent Tree

English | [中文](m2-04-agent-tree.md)

```yaml flow
kind: issue
id: m2-04
milestone: m2
depends:
  - m2-03
priority: P0
status: backlog
scope:
  - apps/api/**
  - fixtures/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr:
adr: []
github:
  number: 36
  url: https://github.com/Shadow-Azure/harness-evolution/issues/36
```

## Background





m2-04 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## Goals





- 完成 m2-04 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## Design authority





- [05 §3.2 Agent 会话树](../../../plans/fullstack-design/05-api-design.md)
- [06 §3.3 agents](../../../plans/fullstack-design/06-database-design.md)
- [07 §2.4 树组装](../../../plans/fullstack-design/07-backend-implementation.md)

## Implementation





- 按 toolUseId 和 subagent transcript 组装 main/subagent/workflow/forked skill 节点
- 预计算节点统计
- 普通 skill 不建节点，forked skill 一行
- 缺 toolUseId 告警

## Implementation steps





1. 先写 nested、forked、缺链、普通 skill 的失败测试
2. 实现树组装
3. 用本地 62 个 subagent 验证挂接

## Dependencies and boundary





- 依赖：m2-03
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:api -- tests/m2-04-agent-tree
pnpm test:db
```

- 树测试通过
- 本地报告 62 个 subagent 均有 parent
- forked skill 计数与 marker 一致

## Acceptance





- 树结构完整且可从任意节点回溯 root
- 统计等于叶子累计

## Gates and CI





- Agent 树单测、本地树对账、结构契约测试

## Non-goals

- No scope creep beyond the listed non-goals and acceptance.
