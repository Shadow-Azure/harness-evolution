# 工作空间总览页面与错误详情下钻

[English](m8-04-workspace-overview-ui.en.md) | 中文

```yaml flow
kind: issue
id: m8-04
milestone: m8
depends:
  - m7-08
  - m8-03
priority: P1
status: backlog
scope:
  - apps/web/src/pages/overview/**
  - apps/web/src/api/**
  - apps/web/src/components/**
  - tests/e2e/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 234
  url: https://github.com/Shadow-Azure/harness-evolution/issues/234
```

## 背景

空间用户需要在一个页面看到来源、趋势和可筛选 bad case 列表，并从列表回到对应错误详情。

## 目标

- 实现 statstrip、来源多选、堆叠趋势和列表。
- URL 保存全部筛选条件。
- 点击 bad case ID 深链到问题描述 Tab。

## 设计依据

- [08 §6](../../../plans/fullstack-design/08-frontend-implementation.md)：总览页面结构。
- [design-v2.md §5](../../../plans/ui-prototype-v2/design-v2.md)：总览原型。

## 实现内容

- 图表使用自研 SVG 和现有 token。
- 时间窗口 >92 天时展示服务端降级粒度。
- 空态区分无数据和筛选无命中。

## 实施步骤

1. 先写筛选恢复与下钻测试。
2. 实现统计条、图表、来源和分页列表。
3. 补加载、空、错误三态 E2E。

## 依赖与交付边界

- 依赖：m7-08、m8-03
- 交付边界：F25 进化对象总览延后到 M11。

## 独立验证

```sh
pnpm test:web; pnpm typecheck:web; pnpm test:e2e -- --pattern overview
```

- 刷新后筛选不变。
- 空 objects 表示全部。
- 下钻 URL 选中正确 case。

## 验收标准

- 页面与原型信息架构一致。
- 图表与列表互不阻塞。

## 门禁与 CI

- Web、E2E、bundle 与 flow 门禁。

## 非目标

- 不引入第三方图表库。
- 不做跨空间汇总。
