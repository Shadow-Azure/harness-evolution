# Top navigation, global states, and demo badge

English | [中文](m1-09-app-shell-states.md)

```yaml flow
kind: issue
id: m1-09
milestone: m1
depends:
  - m1-05
  - m1-08
priority: P1
status: in-progress
scope:
  - AGENTS.md
  - package.json
  - scripts/**
  - tests/**
  - apps/web/**
  - apps/api/**
  - fixtures/**
  - packages/contracts/**
  - .github/workflows/ci.yml
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
  - plans/**
  - reports/**
adr: []
github:
  number: 32
  url: https://github.com/Shadow-Azure/harness-evolution/issues/32
```

## Background





M1 结束时系统还没有领域数据，必须用真实 seed 数据和统一状态样式展示可达的服务边界。

## Goals





- 实现 Sessions/Errors/Evolution 顶部导览和空路由占位。
- 统一 loading/empty/error 三态、全局错误提示和重试。
- 提供 fixtures seed CLI，后端 phase=demo 时顶栏显示演示角标。

## Design authority





- [04 后端架构](../../../plans/fullstack-design/04-backend-architecture.md)

## Implementation





- seed 只写入 M1 可用的基础演示状态，不伪造轨迹或问题。
- 错误提示来自统一 error 对象，禁止运行时 mock。
- 路由占位说明“后续 milestone 提供”。

## Implementation steps





1. 先写三态、重试、角标和导航的组件失败测试。
2. 实现布局组件、seed CLI 和 health phase 联动。
3. 加一条轻量 E2E：登录后看到导航、空态和 demo 角标。

## Dependencies and boundary





- 依赖：m1-05, m1-08
- 交付边界：只做全局壳和演示状态，不提前实现领域页面。

## Verification





```sh
pnpm fixtures:seed
pnpm test:web -- app-shell
pnpm test:e2e -- m1-shell
pnpm build
```

- 空/加载/失败响应分别渲染正确组件并可重试。
- phase=scaffold 无角标，phase=demo 显示角标。

## Acceptance





- 登录用户可导航三大入口且无控制台错误。
- seed 重复执行不产生重复状态。

## Gates and CI





- E2E 冒烟和 seed 幂等测试进入 CI。

## Non-goals

- No fake sessions, problems, or runs.
