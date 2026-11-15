# 进化对象总览前端视角

[English](m11-04-target-overview-ui.en.md) | 中文

```yaml flow
kind: issue
id: m11-04
milestone: m11
depends:
  - m8-04
  - m11-03
priority: P1
status: backlog
scope:
  - apps/web/src/pages/overview/**
  - apps/web/src/components/**
  - tests/e2e/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 219
  url: https://github.com/Shadow-Azure/harness-evolution/issues/219
```

## 背景

总览原型的二级 Tab 展示对象趋势、分布、侧栏列表和单对象分析卡。

## 目标

- 实现 bad case 与进化对象双视角。
- 对象与状态多选驱动趋势。
- 单对象分析使用独立版本和时间筛选。

## 设计依据

- [08 §6.1–§6.3](../../../plans/fullstack-design/08-frontend-implementation.md)：对象总览组件。
- [design-v2.md §5.3](../../../plans/ui-prototype-v2/design-v2.md)：对象视角原型。

## 实现内容

- 共享总览时间上下文，单对象卡可独立覆盖。
- 列表每页 5 个并支持增编删。
- 来源、Session 和状态分布口径可解释。

## 实施步骤

1. 先写 Tab、筛选和分页测试。
2. 实现对象趋势与两块分布。
3. 补知识库对象标签与 E2E。

## 依赖与交付边界

- 依赖：m8-04、m11-03
- 交付边界：P1 扩展。

## 独立验证

```sh
pnpm test:web; pnpm typecheck:web; pnpm test:e2e -- --pattern target-overview
```

- 切 Tab 不重置共享时间窗。
- 单对象卡筛选互不影响。
- 无对象时提示去配置。

## 验收标准

- 页面与原型对象视角一致。
- 图表与列表数值同源。

## 门禁与 CI

- Web、E2E、bundle 与 flow 门禁。

## 非目标

- 不新增图表库。
- 不做用户七点需求之外的自动配置。
