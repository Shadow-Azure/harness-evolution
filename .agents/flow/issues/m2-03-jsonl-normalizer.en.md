# m2-03 Jsonl Normalizer

English | [中文](m2-03-jsonl-normalizer.md)

```yaml flow
kind: issue
id: m2-03
milestone: m2
depends:
  - m2-02
priority: P0
status: backlog
scope:
  - apps/api/**
  - fixtures/**
  - packages/contracts/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr:
adr: []
github:
  number: 35
  url: https://github.com/Shadow-Azure/harness-evolution/issues/35
```

## Background





m2-03 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## Goals





- 完成 m2-03 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## Design authority





- [06 §7.1 用户轮次派生](../../../plans/fullstack-design/06-database-design.md)
- [07 §2 归一化实现](../../../plans/fullstack-design/07-backend-implementation.md)
- [05 §3.3 内部轨迹模型](../../../plans/fullstack-design/05-api-design.md)

## Implementation





- 实现 JSONL 行数组解析和 user_turns/agent_events/消息/token/model 统计
- 单条坏行写入 sync_runs.errors 且隔离
- 只保留统计与锚点，不落消息明细

## Implementation steps





1. 用 fixture 覆盖 assistant/user/attachment/tool/坏行
2. 实现 normalizer 与 parser_version
3. 对本地 4 会话导出统计报告比对原始行数

## Dependencies and boundary





- 依赖：m2-02
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:api -- tests/m2-03-jsonl-normalizer
pnpm test:db
```

- 归一化测试通过
- 本地统计 root/agent 行数与导入基线一致
- 4 个会话均产出模型与用户轮次

## Acceptance





- 坏行不影响整文件
- 所有统计可追溯到 payload 行号

## Gates and CI





- 归一化单测、坏行隔离测试、契约快照

## Non-goals

- No scope creep beyond the listed non-goals and acceptance.
