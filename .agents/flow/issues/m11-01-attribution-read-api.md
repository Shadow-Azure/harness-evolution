# 多归因分页读取与稳定深链 API

[English](m11-01-attribution-read-api.en.md) | 中文

```yaml flow
kind: issue
id: m11-01
milestone: m11
depends:
  - m10-03
priority: P0
status: backlog
scope:
  - apps/api/app/api/problems.py
  - apps/api/app/service/bad_cases/**
  - apps/api/app/db/crud/**
  - packages/contracts/**
  - tests/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 216
  url: https://github.com/Shadow-Azure/harness-evolution/issues/216
```

## 背景

错误详情需要按 bad case 分页列出多个对象 revision 的归因，并恢复单条详情深链。

## 目标

- 返回 attributionCount 与分页列表。
- 单条详情校验 case 归属。
- 保留 V1 probe 兼容读。

## 设计依据

- [05 §3.9、§4.19](../../../plans/fullstack-design/05-api-design.md)：归因 DTO 与端点。
- [06 §4.3](../../../plans/fullstack-design/06-database-design.md)：归因读取口径。

## 实现内容

- 列表按 updated_at 与 attributionId 倒序。
- 跨 case attributionId 返回 404。
- AttributionDetail 返回触发点对照和 evidence warnings。

## 实施步骤

1. 先写分页、跨 case 与兼容测试。
2. 实现 repository 和 DTO。
3. 更新 OpenAPI 与深链示例。

## 依赖与交付边界

- 依赖：m10-03
- 交付边界：不实现错误详情 UI。

## 独立验证

```sh
pnpm test:api -- tests/problems tests/attribution; pnpm contract:check
```

- 同 case 多条归因稳定分页。
- 跨 case 详情 404。
- V1 probe 仍可读。

## 验收标准

- 每条归因有对象 revision 和 run 来源。
- 证据 warning 可显示。

## 门禁与 CI

- API、契约与 flow 门禁。

## 非目标

- 不手动触发单条归因。
- 不把 probe 暴露成主产品概念。
