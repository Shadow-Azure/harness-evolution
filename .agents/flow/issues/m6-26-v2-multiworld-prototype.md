# V2 多工作空间与归因流前端原型

[English](m6-26-v2-multiworld-prototype.en.md) | 中文

```yaml flow
kind: issue
id: m6-26
milestone: m6
depends: []
priority: P1
status: done
scope:
  - plans/ui-prototype-v2/**
  - plans/fullstack-design/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 203
  url: https://github.com/Shadow-Azure/harness-evolution/issues/203
```

## 背景

V2 多工作空间原型在工作空间、总览、Session 搜索、自进化和错误详情上形成可点击基线；后续设计 issue 已把这些交互并入 `plans/fullstack-design`。远端旧 issue 仍处于开放状态，与新流程树形成重复事实。

## 目标

- 记录 V2 前端原型已经交付。
- 把原型纳入 M6 的历史流程对象。
- 让 GitHub 状态与本地 flow tree 一致。

## 设计依据

- [design-v2.md](../../../plans/ui-prototype-v2/design-v2.md)：V2 原型验收说明。
- [15-v1-v2-gap-analysis.md](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md)：V2 目标态与实现差距。

## 实现内容

- 保留 `plans/ui-prototype-v2/harness-evolution.html` 作为多工作空间、总览和归因流程的可点击基线。
- 由设计文档承接原型中的鉴权、空间、上报、总览、自进化和多归因目标态。
- 本 issue 只完成历史记录与状态收口，不新增实现范围。

## 实施步骤

1. 核对原型文件和 V2 设计文档已经合入 main。
2. 将 issue #203 纳入 M6 流程树并标记 done。
3. 运行 flow 同步关闭对应远端 issue。

## 依赖与交付边界

- 依赖：无
- 交付边界：仅原型与设计资产，不包含生产前端实现。

## 独立验证

```sh
pnpm verify:flow; pnpm lint:docs
```

- V2 原型文件存在，flow 与文档门禁通过。

## 验收标准

- issue #203 可由本地流程树追溯到 M6。
- M7–M11 的实现 issue 继续复用原型而不复制原型资产。

## 门禁与 CI

- `pnpm verify:flow` 与 `pnpm lint:docs` 必须通过。

## 非目标

- 不修改原型视觉。
- 不把原型打桩数据带入生产代码。
