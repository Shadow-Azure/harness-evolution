# m2-04 agent tree

[English](m2-04-agent-tree.en.md) | 中文

```yaml flow
kind: issue
id: m2-04
milestone: m2
depends:
  - m2-03
priority: P0
status: in-progress
scope:
  - apps/api/**
  - fixtures/**
  - docs/**
  - scripts/**
  - package.json
  - AGENTS.md
  - .agents/flow/**
  - .agents/notes/**
  - plans/**
  - reports/**
adr: []
github:
  number: 36
  url: https://github.com/Shadow-Azure/harness-evolution/issues/36
```

## 背景

m2-04 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## 目标

- 完成 m2-04 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## 设计依据

- [05 §3.2 Agent 会话树](../../../plans/fullstack-design/05-api-design.md)
- [06 §3.3 agents](../../../plans/fullstack-design/06-database-design.md)
- [07 §2.4 树组装](../../../plans/fullstack-design/07-backend-implementation.md)

## 实现内容

- 按 toolUseId 和 subagent transcript 组装 main/subagent/workflow/forked skill 节点
- 预计算节点统计
- 普通 skill 不建节点，forked skill 一行
- 缺 toolUseId 告警

## 实施步骤

1. 先写 nested、forked、缺链、普通 skill 的失败测试
2. 实现树组装
3. 用本地 62 个 subagent 验证挂接

## 依赖与交付边界

- 依赖：m2-03
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## 独立验证

```sh
pnpm test:api -- tests/m2-04-agent-tree
pnpm test:db
```

- 树测试通过
- 本地报告 62 个 subagent 均有 parent
- forked skill 计数与 marker 一致

## 验收标准

- 树结构完整且可从任意节点回溯 root
- 统计等于叶子累计

## 门禁与 CI

- Agent 树单测、本地树对账、结构契约测试

## 非目标

- 不渲染前端
