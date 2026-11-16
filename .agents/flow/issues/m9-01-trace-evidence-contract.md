# 轨迹证据契约、关系置信度与完成状态迁移

[English](m9-01-trace-evidence-contract.en.md) | 中文

```yaml flow
kind: issue
id: m9-01
milestone: m9
depends:
  - m9-06
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

当前树状态不能表达父工具未返回、子 Agent 无最终报告和外部 attempt 失败，关系也只有 linked/unlinked。M9-06 已建立 runtime 身份与 parser 工厂，但还没有统一字段承载 execution_outcome、relation_confidence、对象 revision、agent/skill 定义指纹和文件读取证据。

## 目标

- 增加 execution_outcome、end_reason、relation_confidence 等证据字段。
- 增加 object_revision、runtime_version、agent_definition_hash、skill_definition_hash 和 model evidence。
- 增加文件读取证据：path、range、complete、content hash；不保存原文。
- 保持 parser_version、runtime_version 与定义指纹分离。

## 设计依据

- [15 §9.1–§9.4](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md#91-父子关系证据)：关系、revision、触发与完成状态。
- [06 §3.0.1 runtime 身份](../../../plans/fullstack-design/06-database-design.md#301-runtime-身份与-parser-版本)：runtime_key 与 per-runtime parser_version。
- [06 §3.3–§3.4、§9](../../../plans/fullstack-design/06-database-design.md)：轨迹表演进。

## 实现内容

- 扩展 agents/session_families/agent_events 的稳定字段：execution_outcome、end_reason、relation_confidence、object_revision、definition_hash、file_read_hash、read_complete。
- 在 session_families 保存执行完成度而不覆盖解析健康。
- 为新增状态定义封闭 API 枚举和迁移回填；存量统一回填 legacy_unknown。
- runtime_key 由 m9-06 提供；本 issue 不重复建 runtime 表。

## 实施步骤

1. 先写双方言迁移与会话 DTO 失败测试。
2. 实现列、索引、默认值和回填。
3. 更新 OpenAPI、契约快照与证据 DTO。
4. 补旧数据回填与未知状态测试。

## 依赖与交付边界

- 依赖：m9-06
- 交付边界：只建立数据契约与 DTO，不解析新证据。

## 独立验证

```sh
pnpm test:db; pnpm test:db:mysql; pnpm contract:check
```

- 存量行回填为 legacy_unknown。
- 定义/文件 hash 可空，非空边界符合设计。
- 双方言升级可重复。
- runtime_key 与 parser_version 可同时保存且互不覆盖。

## 验收标准

- 证据字段可同时表达解析健康、执行闭环、对象定义和文件读取。
- 契约不含自由文本状态。
- 没有保存消息、工具输出或定义正文。

## 门禁与 CI

- 数据库、契约与 flow 门禁。

## 非目标

- 不推断对象版本。
- 不修改归因表。
- 不实现 parser 或第二个 runtime。
