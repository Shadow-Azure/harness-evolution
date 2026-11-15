# Session 前端最新 10 条与回车查询

[English](m8-05-session-latest-ten-ui.en.md) | 中文

```yaml flow
kind: issue
id: m8-05
milestone: m8
depends:
  - m7-08
  - m8-02
priority: P1
status: backlog
scope:
  - apps/web/src/pages/sessions/**
  - apps/web/src/api/**
  - tests/e2e/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 235
  url: https://github.com/Shadow-Azure/harness-evolution/issues/235
```

## 背景

当前 Session 页默认拉取过多数据，并把搜索当成防抖筛选；V2 要改成最新 10 条和显式提交。

## 目标

- 初次只请求 limit=10。
- root session ID 回车后重新查询。
- 清空输入再回车恢复最新 10 条。

## 设计依据

- [08 §5.2.1](../../../plans/fullstack-design/08-frontend-implementation.md)：最新 10 条与空态。
- [05 §4.18](../../../plans/fullstack-design/05-api-design.md)：q 与 limit。

## 实现内容

- 搜索改为 Enter 或按钮提交。
- 标题显示最新 10 / 总数和待同步角标。
- 未命中时清空右侧选中态。

## 实施步骤

1. 先写请求次数和回车测试。
2. 改造列表查询与空态。
3. 补跨空间和恢复列表 E2E。

## 依赖与交付边界

- 依赖：m7-08、m8-02
- 交付边界：不改错误详情内部。

## 独立验证

```sh
pnpm test:web; pnpm typecheck:web; pnpm test:e2e -- --pattern session-latest-ten
```

- 输入变化不触发请求。
- 回车只触发一次查询。
- 未命中不保留旧详情。

## 验收标准

- 首屏最多 10 条。
- 查询与空态符合原型。

## 门禁与 CI

- Web、E2E 与 flow 门禁。

## 非目标

- 不做实时模糊搜索。
- 不默认加载全量 Session。
