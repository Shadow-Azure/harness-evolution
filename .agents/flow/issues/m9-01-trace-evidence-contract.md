# 轨迹证据契约、关系置信度与完成状态迁移

[English](m9-01-trace-evidence-contract.en.md) | 中文

```yaml flow
kind: issue
id: m9-01
milestone: m9
depends:
  - m7-02
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
  number: 236
  url: https://github.com/Shadow-Azure/harness-evolution/issues/236
```

## 背景

当前树状态不能表达父工具未返回、子 Agent 无最终报告和外部 attempt 失败，关系也只有 linked/unlinked。

## 目标

- 增加 execution_outcome、end_reason、relation_confidence 等证据字段。
- 增加 object_revision、runtime_version 和 model evidence。
- 保持 parser_version 与 runtime_version 分离。

## 设计依据

- [15 §9.1–§9.4](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md)：真实会话证据门禁。
- [06 §3.3–§3.4、§9](../../../plans/fullstack-design/06-database-design.md)：轨迹表演进。

## 实现内容

- 扩展 agents 与 agent_events 的稳定字段。
- 在 session_families 保存执行完成度而不覆盖解析健康。
- 为新增状态定义封闭 API 枚举和迁移回填。

## 实施步骤

1. 先写双方言迁移与会话 DTO 失败测试。
2. 实现列、索引和默认值。
3. 更新 OpenAPI 与契约快照。

## 依赖与交付边界

- 依赖：m7-02
- 交付边界：只建立数据契约，不解析新证据。

## 独立验证

```sh
pnpm test:db; pnpm test:db:mysql; pnpm contract:check
```

- 存量行回填为 legacy_unknown。
- 新列可空/非空边界符合设计。
- 双方言升级可重复。

## 验收标准

- 证据字段可同时表达解析健康与执行闭环。
- 契约不含自由文本状态。

## 门禁与 CI

- 数据库、契约与 flow 门禁。

## 非目标

- 不推断对象版本。
- 不修改归因表。
