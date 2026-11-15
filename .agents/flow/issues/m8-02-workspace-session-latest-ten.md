# 空间 Session 投影、最新 10 条与回车查询

[English](m8-02-workspace-session-latest-ten.en.md) | 中文

```yaml flow
kind: issue
id: m8-02
milestone: m8
depends:
  - m7-06
  - m8-01
priority: P0
status: in-progress
scope:
  - apps/api/app/api/sessions.py
  - apps/api/app/service/sessions/**
  - apps/api/app/db/crud/sessions.py
  - apps/api/tests/**
  - packages/contracts/**
  - tests/**
  - .agents/flow/**
  - .agents/notes/**
  - plans/**
adr: []
github:
  number: 232
  url: https://github.com/Shadow-Azure/harness-evolution/issues/232
```

## 背景

空间 Session 页面默认只应加载最新 10 条，并支持按 root session ID 回车精确查询。

## 目标

- 返回 limit=10、total 与 pendingSessions。
- q 使用 root session ID 查询。
- 搜索未命中时左右两侧都有明确空态。

## 设计依据

- [05 §3.10、§4.18](../../../plans/fullstack-design/05-api-design.md)：空间 Session DTO。
- [08 §5.2.1](../../../plans/fullstack-design/08-frontend-implementation.md)：最新 10 条交互。

## 实现内容

- 空间 Session 集合来自 bad_cases 根会话投影。
- 按 updated/started 规则稳定排序。
- 响应区分 total 与待轨迹同步数量。

## 实施步骤

1. 先写默认 limit、搜索和跨空间测试。
2. 实现投影查询与分页契约。
3. 补空态字段和性能索引验证。

## 依赖与交付边界

- 依赖：m7-06、m8-01
- 交付边界：不改前端布局。

## 独立验证

```sh
pnpm test:api -- tests/sessions; pnpm contract:check
```

- 无 q 时最多 10 条。
- 完整 root ID 命中正确 Session。
- 跨空间搜索结果为空或 404。

## 验收标准

- 前端不需要额外过滤即可展示最新 10。
- 待同步 Session 有独立计数。

## 门禁与 CI

- API、数据库、契约与 flow 门禁。

## 非目标

- 不返回全量 Session。
- 不按消息正文搜索。
