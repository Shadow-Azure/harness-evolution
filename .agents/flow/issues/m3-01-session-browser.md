# m3-01 session browser

[English](m3-01-session-browser.en.md) | 中文

```yaml flow
kind: issue
id: m3-01
milestone: m3
depends:
  - m2-06
  - m2-07
priority: P0
status: done
scope:
  - AGENTS.md
  - apps/web/**
  - packages/contracts/**
  - fixtures/**
  - scripts/**
  - tests/**
  - .github/workflows/ci.yml
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
  - plans/**
  - reports/**
adr: []
github:
  number: 41
  url: https://github.com/Shadow-Azure/harness-evolution/issues/41
```

## 背景

m3-01 把真实 canonical Session 数据接到原型的两栏浏览界面，用户需要在一屏内完成分诊、搜索、筛选和选中概览。

## 目标

- 实现 360px Session 浏览栏、真实白卡、双密度条和右侧 Session 概览。
- 搜索、状态、排序和选中 Session 全部写入 URL，刷新与前进后退可恢复。
- 列表和概览分别具备 loading、empty、error/retry，不请求未实现的 Agent tree。
- 问题数使用真实 `stats.badCases`，不伪造 count 或前端数据。

## 设计依据

- [03 §5 Session 浏览器](../../../plans/fullstack-design/03-frontend-architecture.md)
- [08 §5 组件树](../../../plans/fullstack-design/08-frontend-implementation.md)
- [02 §2.1 F3/F4](../../../plans/fullstack-design/02-features.md)
- [原型验收基准](../../../plans/14-15-ui-prototype/harness-evolution.html)

## 实现内容

- 原型左侧 Session 卡：状态点、标题、时间、repo、时长、工具/子 Agent、五项统计和两条密度线。
- 原型右侧概览：标题/meta/状态徽章、九项统计、Token 可读格式，以及执行流后续占位。
- 300ms 搜索防抖、状态 chips、排序、首项自动选中和 `/sessions/:sid` 深链。
- 原型亮色 token、1408px 两栏与 390px 单列布局。

## 实施步骤

1. 先用 MSW 和真实 fixture seed 写组件/E2E 失败测试。
2. 实现 sessions API/query、列表卡、概览和 URL 状态。
3. 用真实 4 Session 数据完成 computed-style、URL 恢复和响应式验收。

## 依赖与交付边界

- 依赖：m2-06, m2-07
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## 独立验证

```sh
pnpm test:api -- tests/m3-01-session-browser
pnpm test:db
pnpm test:web
pnpm test:e2e -- m3-session-browser
```

- CI seed E2E 通过
- 本地会话列表和概览与 API 统计一致

## 验收标准

- 刷新后搜索、排序、选中 session 恢复
- 三态可重试

## 门禁与 CI

- 组件测试、query gate、真实 Chrome E2E 与原型 computed-style 回归。

## 非目标

- 不画执行流图
