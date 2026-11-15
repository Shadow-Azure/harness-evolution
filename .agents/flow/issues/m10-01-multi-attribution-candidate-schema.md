# 多归因、缓存与候选快照迁移

[English](m10-01-multi-attribution-candidate-schema.en.md) | 中文

```yaml flow
kind: issue
id: m10-01
milestone: m10
depends:
  - m9-01
  - m9-04
priority: P0
status: backlog
scope:
  - apps/api/app/db/**
  - apps/api/alembic/**
  - packages/contracts/**
  - tests/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 210
  url: https://github.com/Shadow-Azure/harness-evolution/issues/210
```

## 背景

一 case 多归因、归因缓存和可解释候选需要原位演进既有表，并保留历史 probe 读取链。

## 目标

- 移除 bad_case_analysis case 唯一约束。
- 扩展 probe_reports 的结论、revision 和缓存字段。
- 新增 evolution_run_candidates。

## 设计依据

- [06 §4.2、§5.8–§5.10、§9](../../../plans/fullstack-design/06-database-design.md)：归因、缓存与候选结构。
- [15 §6.1](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md)：契约与迁移顺序。

## 实现内容

- 缓存键包含 workspace、case、对象身份、revision、策略和引擎。
- 候选全量保存 included=false 行。
- 历史 nonissue 以 legacy-probe-import 标记。

## 实施步骤

1. 先写一对多与缓存 upsert 测试。
2. 实现第二组迁移和 repository。
3. 更新 OpenAPI 与快照。

## 依赖与交付边界

- 依赖：m9-01、m9-04
- 交付边界：不调用归因引擎。

## 独立验证

```sh
pnpm test:db; pnpm test:db:mysql; pnpm contract:check
```

- 同 case 可关联多条归因。
- 同缓存键原子 upsert。
- 候选唯一键按 run+case 幂等。

## 验收标准

- 既有表名保留。
- 历史 row 可兼容读取。

## 门禁与 CI

- 数据库、契约与 flow 门禁。

## 非目标

- 不新增平行归因表。
- 不迁移被否 history 语义。
