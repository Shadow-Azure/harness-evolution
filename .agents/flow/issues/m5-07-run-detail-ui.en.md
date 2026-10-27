# m5-07 Run Detail Ui

English | [中文](m5-07-run-detail-ui.md)

```yaml flow
kind: issue
id: m5-07
milestone: m5
depends:
  - m5-04
  - m5-06
priority: P0
status: in-progress
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - fixtures/**
  - docs/**
  - plans/**
  - plans/fullstack-design/**
  - .agents/flow/**
  - .agents/notes/**
  - tests/e2e/**
adr: []
github:
  number: 56
  url: https://github.com/Shadow-Azure/harness-evolution/issues/56
```

## Background





m5-07 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## Goals





- 完成 m5-07 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## Design authority





- [08 §10 运行详情](../../../plans/fullstack-design/08-frontend-implementation.md)
- [03 §8 组件](../../../plans/fullstack-design/03-frontend-architecture.md)
- [02 F12/F13](../../../plans/fullstack-design/README.md)

## Implementation





- 实现 stepper、六步内容、聚类卡、迭代卡、diff、eval、candidate ref/commit 和阻塞态
- 未到达不可点

## Implementation steps





1. 用六步 fixture 写组件失败测试
2. 实现页面与状态映射
3. E2E 覆盖 completed/blocked

## Dependencies and boundary





- 依赖：m5-04, m5-06
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。
- run-detail 读模型补齐六步状态、workspace、blocked/retry/eval 上下文，使前端直接消费后端状态；E2E fixture 覆盖 running/blocked/completed。
- 设计文档面仅允许修正与 HTML 原型冲突的六步标题口径，不扩张功能范围或放宽验收标准。
- `plans/` is limited to this PR's structured review record and does not change product-design facts.

## Verification





```sh
pnpm test:api -- tests/m5-07-run-detail-ui
pnpm test:db
pnpm test:web
pnpm test:e2e
pnpm contract:check
```

- 详情与 API 六步一致
- 未到达禁用并有提示

## Acceptance





- 用户可读懂每轮输入/输出与 candidate 位置

## Gates and CI





- 组件测试、E2E、contract gate

## Non-goals

- No scope creep beyond the listed non-goals and acceptance.
