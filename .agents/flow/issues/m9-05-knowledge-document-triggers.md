# 知识库文档触发点识别

[English](m9-05-knowledge-document-triggers.en.md) | 中文

```yaml flow
kind: issue
id: m9-05
milestone: m9
depends:
  - m9-01
  - m9-02
  - m9-04
priority: P0
status: in-progress
scope:
  - apps/api/alembic/**
  - apps/api/app/service/acquisition/**
  - apps/api/app/service/sessions/**
  - apps/api/app/service/workspaces/**
  - apps/api/app/db/**
  - apps/api/app/api/**
  - apps/api/app/utils/**
  - apps/api/app/errors.py
  - packages/contracts/**
  - fixtures/**
  - tests/**
  - apps/api/tests/**
  - apps/web/src/api/**
  - apps/web/src/pages/workspaces/**
  - plans/fullstack-design/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 240
  url: https://github.com/Shadow-Azure/harness-evolution/issues/240
```

## 背景

当前实现只识别 Skill、Agent、Workflow；Read、知识库搜索和 MCP retrieval 不会进入 agent_events，object_type 也仅允许 skill|agent。

## 目标

- 识别配置知识根、Provider 或 Collection 返回的文档。
- 保存 document id、revision、path、retrieval kind 和触发坐标。
- 普通源码 Read 不误判为知识库触发。

## 设计依据

- [15 §9.3](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md)：知识库触发边界。
- [06 §3.4、§7.5](../../../plans/fullstack-design/06-database-design.md)：事件与对象进入点。

## 实现内容

- 迁移 0019：`agent_events` 增加 document id/revision/path/retrieval kind/scope 五列与 `(agent_id, kind, document_id)` 索引；`workspaces` 增加 `knowledge_roots` JSON 配置。知识事件不扩 `bad_cases.object_type` / `evolution_targets.object_type`。
- Read 需命中工作空间知识根才转换成 `kind=knowledge`；Edit/Bash 不生成。
- MCP 知识工具按 adapter 显式白名单识别，只存 id/revision/path/kind/scope/hash，不存正文、chunk 与原始响应。
- Session API 暴露 knowledge 事件与文档证据；parser 4 → 5 重放 claude-code 存量。

## 实施步骤

1. 先寫源码 Read 不得命中与知识 Read 命中的成对测试。
2. 实现配置、adapter、事件和 API DTO。
3. 增加文档 revision 与检索范围证据。

## 依赖与交付边界

- 依赖：m9-01、m9-02、m9-04
- 交付边界：可先只作为归因证据，不强制成为可进化对象。

## 独立验证

```sh
pnpm test:api -- tests/m9-05-knowledge-document-triggers; pnpm contract:check
```

- 知识根内 Read 生成 knowledge 事件。
- 普通源码 Read 不生成。
- MCP 返回多文档时可稳定排序。

## 验收标准

- Skill、Agent 和 knowledge 使用同一触发坐标口径。
- 文档全文与 chunk 不落库。

## 门禁与 CI

- API、契约、fixture、隐私与 flow 门禁。

## 非目标

- 不保存文档正文。
- 不实现知识库自进化 patch。
