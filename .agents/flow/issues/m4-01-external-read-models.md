# m4-01 external read models

[English](m4-01-external-read-models.en.md) | 中文

```yaml flow
kind: issue
id: m4-01
milestone: m4
depends:
  - m3-05
priority: P0
status: done
scope:
  - apps/api/**
  - apps/api/alembic/**
  - fixtures/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
  - plans/**
  - reports/**
  - tests/**
adr: []
github:
  number: 46
  url: https://github.com/Shadow-Azure/harness-evolution/issues/46
```

## 背景

m4-01 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## 目标

- 完成 m4-01 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## 设计依据

- [06 §4 外部只读表](../../../plans/fullstack-design/06-database-design.md)
- [05 §3.4 问题模型](../../../plans/fullstack-design/05-api-design.md)
- [09 R2 风险](../../../plans/fullstack-design/README.md)

## 实现内容

- 创建 bad_cases/analysis/probe_reports 只读映射与五态 fixtures
- 实现缺失字段降级、防御校验和只读约束

## 实施步骤

1. 写五态、缺失字段、不一致状态的失败测试
2. 实现只读 repository
3. 确保 Alembic 不写外部表

## 依赖与交付边界

- 依赖：m3-05
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## 独立验证

```sh
pnpm test:api -- tests/m4-01-external-read-models
pnpm test:db
pnpm test:db:mysql
pnpm fixtures:check
```

- 双方言查询通过
- 五态 fixture 与真实只读行保持同构
- 五态与降级路径断言完整

## 验收标准

- 外部字段漂移不会崩溃且日志可定位

## 门禁与 CI

- 双方言 gate、fixture schema gate、只读 lint/测试

## 非目标

- 不允许服务写外部表
