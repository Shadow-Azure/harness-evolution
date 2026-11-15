# 工作空间 bad case 总览聚合 API

[English](m8-03-workspace-overview-api.en.md) | 中文

```yaml flow
kind: issue
id: m8-03
milestone: m8
depends:
  - m8-02
priority: P0
status: done
scope:
  - apps/api/app/api/overview.py
  - apps/api/app/service/overview/**
  - apps/api/app/db/crud/**
  - apps/api/app/main.py
  - apps/api/app/errors.py
  - apps/api/tests/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 233
  url: https://github.com/Shadow-Azure/harness-evolution/issues/233
```

## 背景

总览需要按 object_name、时间维度和 self/discovery 聚合，并支持任意组合筛选的分页列表。

## 目标

- 提供 summary、trend、sources 和 bad-case 列表。
- 对象多选为空表示全部。
- 时间桶补零并支持日周月粒度。

## 设计依据

- [05 §3.10、§4.18](../../../plans/fullstack-design/05-api-design.md)：总览 DTO 与端点。
- [06 §7.5](../../../plans/fullstack-design/06-database-design.md)：时间与空间口径。

## 实现内容

- 所有查询按 workspace_id 过滤。
- summary 返回额度、来源、Session 和两类 bad case。
- 列表支持 from/to、objects、badCaseType 和 page。

## 实施步骤

1. 先写 SQL 手算对照和空桶测试。
2. 实现聚合服务与 SQL 分页。
3. 补筛选上限、窗口和粒度错误码。

## 依赖与交付边界

- 依赖：m8-02
- 交付边界：不实现对象视角和图表组件。

## 独立验证

```sh
pnpm test:api -- tests/overview; pnpm test:db:mysql
```

- 多选对象取并集，空选择不加限制。
- 日周月空桶补零。
- 列表过滤可全部留空。

## 验收标准

- 聚合数字与 SQL 手算一致。
- 所有响应只含当前空间数据。

## 门禁与 CI

- API、MySQL、契约与 flow 门禁。

## 非目标

- 不做图表渲染。
- 不做进化对象视角。
