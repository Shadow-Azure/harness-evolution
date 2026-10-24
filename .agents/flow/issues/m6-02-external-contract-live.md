# m6-02 external contract live

[English](m6-02-external-contract-live.en.md) | 中文

```yaml flow
kind: issue
id: m6-02
milestone: m6
depends:
  - m5-11
priority: P1
status: backlog
scope:
  - apps/api/**
  - apps/api/alembic/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 62
  url: https://github.com/Shadow-Azure/harness-evolution/issues/62
```

## 背景

m6-02 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## 目标

- 完成 m6-02 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## 设计依据

- [06 §4 外部表](../../../plans/fullstack-design/06-database-design.md)
- [09 R2 风险](../../../plans/fullstack-design/README.md)
- [05 §4.7 问题 API](../../../plans/fullstack-design/05-api-design.md)

## 实现内容

- 联调真实 bad_case/probe 表，建立字段/状态漂移探测、降级与告警
- 确认只读权限

## 实施步骤

1. 写真实 schema contract 测试和 drift fixture
2. 接入监控日志
3. 验证权限不足可诊断

## 依赖与交付边界

- 依赖：m5-11
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## 独立验证

```sh
pnpm test:api -- tests/m6-02-external-contract-live
pnpm test:db
```

- 外部真实表可读
- 漂移被记录且 UI 降级

## 验收标准

- 生产联调不破坏只读边界

## 门禁与 CI

- external contract gate、read-only tests

## 非目标

- 不修复上游数据
