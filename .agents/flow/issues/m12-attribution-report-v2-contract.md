# 归因报告 V2 契约、执行清单与缓存语义

[English](m12-attribution-report-v2-contract.en.md) | 中文

```yaml flow
kind: issue
id: m12-14
milestone: m12
depends:
  - m10-03
  - m11-01
priority: P0
status: done
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - docs/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 317
  url: https://github.com/Shadow-Azure/harness-evolution/issues/317
```

## 背景

现有 `probe_reports` 只承载 `attributed|non_target`、三类 `attribute_type` 和两段文本，缓存键也只包含空间、Badcase、对象、revision、策略与引擎。可插拔 Agent Skill 归因还需要结构化证据、引入点、检测点、Skill/模型/上下文版本和每次执行状态；若不先统一报告契约，后续 Skill、执行器、页面和聚类会分别发明字段并误用旧缓存。

## 目标

- 保留 `probe_reports` 为归因报告唯一事实源，定义向后兼容的 V2 结构化报告。
- 定义执行状态、归因结论、分类、证据与执行清单的边界。
- 让缓存身份覆盖实际影响结论的 Skill、模型、上下文和 schema 版本。

## 设计依据

- [06 §4.2、§5.8](../../../plans/fullstack-design/06-database-design.md)：多归因、Probe Report 与缓存语义。
- [07 §5.13](../../../plans/fullstack-design/07-backend-implementation.md)：归因引擎和 Runner 边界。
- [05 §3.9、§4.19](../../../plans/fullstack-design/05-api-design.md)：归因公开契约与读取 API。

## 实现内容

- 定义 `report_schema_version` 与结构化 payload，包含选定对象、结论、分类维度、引入点、检测点、证据、分析、建议线索和 warning。
- 明确 `attributed|non_target|inconclusive` 与 queued/running/succeeded/blocked/failed 等执行状态互不替代；最终枚举以设计评审结论为准。
- 增加不可变执行清单，记录 engine、Skill revision/content hash、模型配置指纹、上下文 snapshot hash 与输出 schema。
- 将缓存键改为规范化执行清单 hash；旧七元组与 legacy probe 保持兼容读取。
- 评估并实现 `attribution_executions` 审计表；它只记录执行尝试，不成为平行归因报告表。

## 实施步骤

1. 写报告 schema、结论/状态真值表和缓存失效测试。
2. 更新迁移、repository、OpenAPI 与生成类型。
3. 更新归因读 API 和现有页面对未知/不确定字段的降级。
4. 补 SQLite/MySQL、legacy migration 与并发缓存测试。

## 依赖与交付边界

- 依赖：m10-03、m11-01。
- 交付边界：定义并落地报告、执行清单和缓存事实；不调用 LLM，不实现 Skill 注册或完整 Trace 上下文。

## 独立验证

```sh
pnpm test:api -- tests/attribution
pnpm test:db
pnpm test:db:mysql
pnpm contract:check
```

- Skill、模型、上下文或 schema 任一变化都会得到不同缓存身份。
- 旧报告继续可读，V2 报告可稳定往返结构化字段。

## 验收标准

- 同一 Badcase 对同一对象 revision 可保存一份当前有效 V2 报告，并追溯生成它的执行清单。
- 执行失败不会被写成 `non_target`，证据不足不会伪造成确定结论。
- 缓存命中可解释其 Skill、模型和上下文版本。

## 门禁与 CI

- API、双库迁移、契约、文档与 Flow 门禁。

## 非目标

- 不新增第二套归因报告主表或第二套公开 ID。
- 不保存完整原始 Session Trace。
- 不实现内网模型 adapter、Skill 编辑器或聚类算法。
