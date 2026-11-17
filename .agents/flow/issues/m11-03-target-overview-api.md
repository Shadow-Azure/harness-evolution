# 进化对象总览聚合 API

[English](m11-03-target-overview-api.en.md) | 中文

```yaml flow
kind: issue
id: m11-03
milestone: m11
depends:
  - m10-02
  - m10-03
priority: P1
status: in-progress
scope:
  - apps/api/app/api/overview.py
  - apps/api/app/service/overview/**
  - apps/api/app/db/crud/**
  - apps/api/app/main.py
  - apps/api/tests/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 218
  url: https://github.com/Shadow-Azure/harness-evolution/issues/218
```

## 背景

原型包含按进化对象查看关联 Session、潜在 case 和归因三态的视角，但不属于用户七点需求的 P0 主链路。

## 目标

- 返回对象列表、趋势、case 列表和单对象分析。
- 潜在数与 M10 matcher 完全一致。
- 支持 revision 和知识库对象。

## 设计依据

- [05 §3.10、§4.18](../../../plans/fullstack-design/05-api-design.md)：对象总览 DTO。
- [08 §6.1](../../../plans/fullstack-design/08-frontend-implementation.md)：对象视角结构。

## 实现内容

- attributed/nonTarget/unanalyzed 从归因行去重。
- 趋势按归因时间与上报时间分别落桶。
- 列表按 evolvable 降序。

## 实施步骤

1. 先写三态去重与空缓存测试。
2. 实现目标聚合和分页。
3. 补知识库 target 用例。

## 依赖与交付边界

- 依赖：m10-02、m10-03
- 交付边界：P1 扩展，不阻塞七点 V2 核心验收。

## 独立验证

```sh
pnpm test:api -- tests/overview; pnpm contract:check
```

- attributed+nonTarget+unanalyzed=potential。
- 多 revision 去重正确。
- 潜在数与向导一致。

## 验收标准

- 对象视角只读空间内数据。
- 知识对象可按同一坐标比较。

## 门禁与 CI

- API、契约、性能与 flow 门禁。

## 非目标

- 不做跨空间对象排行。
- 不做人工手工改归因状态。
