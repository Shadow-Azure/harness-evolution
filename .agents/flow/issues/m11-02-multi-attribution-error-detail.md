# 错误详情可折叠多归因左栏

[English](m11-02-multi-attribution-error-detail.en.md) | 中文

```yaml flow
kind: issue
id: m11-02
milestone: m11
depends:
  - m7-08
  - m10-05
  - m11-01
priority: P0
status: in-progress
scope:
  - apps/web/src/pages/errors/**
  - apps/web/src/components/**
  - apps/web/src/api/**
  - apps/web/src/composables/**
  - apps/web/src/router/**
  - apps/web/src/utils/**
  - apps/web/src/test/**
  - packages/contracts/**
  - plans/**
  - tests/e2e/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 217
  url: https://github.com/Shadow-Azure/harness-evolution/issues/217
```

## 背景

一个 bad case 现在可以对应多个对象 revision 和多条归因，旧左栏单卡片结构无法承载。

## 目标

- 父层为可折叠 bad case 组。
- 组内归因按 2 条分页。
- 父行进问题描述、子项进归因分析并深链恢复。

## 设计依据

- [08 §7](../../../plans/fullstack-design/08-frontend-implementation.md)：多归因错误详情。
- [design-v2.md §8](../../../plans/ui-prototype-v2/design-v2.md)：原型交互。

## 实现内容

- 增加 CaseGroup 和 AttributionItem。
- URL 使用 case、tab、at。
- 无归因时提供以 case 启动自进化入口。

## 实施步骤

1. 先写展开、翻页与深链测试。
2. 重写左栏与归因报告。
3. 补跨空间、空态和键盘 E2E。

## 依赖与交付边界

- 依赖：m7-08、m10-05、m11-01
- 交付边界：执行流 DAG/结构树布局由 m11-07 承接，本 issue 不改执行流布局。
- 本 issue 消费 m11-01 的归因契约与 `at` 深链，故 scope 覆盖 `apps/web/src/{router,utils,composables,test}/**`、`packages/contracts/**` 与检视记录所在的 `plans/**`。

## 独立验证

```sh
pnpm test:web; pnpm typecheck:web; pnpm test:e2e -- --pattern multi-attribution
```

- 一个 case 可展开多条归因。
- 刷新恢复 case 与 at。
- 普通用户不出现启动入口。

## 验收标准

- 非该对象问题与未分析文案严格区分。
- 切换空间不复用旧详情。

## 门禁与 CI

- Web、E2E、bundle 与 flow 门禁。

## 非目标

- 不做手动单条归因。
- 不用整行点击代替明确链接。
