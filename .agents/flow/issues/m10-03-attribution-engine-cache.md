# 对象级归因引擎、缓存与候选写入

[English](m10-03-attribution-engine-cache.en.md) | 中文

```yaml flow
kind: issue
id: m10-03
milestone: m10
depends:
  - m10-01
  - m10-02
priority: P0
status: backlog
scope:
  - apps/api/app/service/evolution/**
  - apps/api/app/db/crud/**
  - packages/contracts/**
  - tests/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 212
  url: https://github.com/Shadow-Azure/harness-evolution/issues/212
```

## 背景

潜在 case 需要按对象 revision 生成可复用归因，并区分 attributed、non_target 与未分析。

## 目标

- 实现 AttributionEngine 协议与 rule-v1 占位引擎。
- 实现缓存命中、重算和复用计数。
- 将候选和归因关联原子写入。

## 设计依据

- [07 §5.13](../../../plans/fullstack-design/07-backend-implementation.md)：归因生成与缓存。
- [06 §4.2、§5.8](../../../plans/fullstack-design/06-database-design.md)：缓存语义。

## 实现内容

- 引擎保持纯函数，缓存与 upsert 由 runner 负责。
- non_target 保留但不进簇。
- knowledge 证据可作为 category 和 reasoning 依据。

## 实施步骤

1. 先写缓存命中、关闭与并发 upsert 测试。
2. 实现 engine registry、runner 和 repository。
3. 补 blocked(attribution) 重试。

## 依赖与交付边界

- 依赖：m10-01、m10-02
- 交付边界：不实现真实 LLM 排名。

## 独立验证

```sh
pnpm test:api -- tests/attribution; pnpm test:db; pnpm test:db:mysql
```

- 第二次运行 reused 数正确。
- 缓存关闭覆盖同键结论。
- non_target 可见但不进簇。

## 验收标准

- 结论只作用于对象 revision。
- 归因失败可恢复。

## 门禁与 CI

- API、数据库、契约与 flow 门禁。

## 非目标

- 不修改 bad case 本身。
- 不声称占位归因是最终模型。
