# 前端空间壳、路由守卫与缓存隔离

[English](m7-08-workspace-shell-routing.en.md) | 中文

```yaml flow
kind: issue
id: m7-08
milestone: m7
depends:
  - m7-04
  - m7-06
  - m7-07
priority: P1
status: done
scope:
  - apps/web/src/**
  - packages/contracts/**
  - tests/e2e/**
  - tests/integration/**
  - .agents/flow/**
  - .agents/notes/**
  - plans/**
  - reports/**
adr:
  - ../../notes/implemented/architecture/2026-11-15-workspace-shell-routing.md
github:
  number: 229
  url: https://github.com/Shadow-Azure/harness-evolution/issues/229
```

## 背景

所有 V2 页面都需要稳定的空间上下文；旧路由不能静默选择任意空间。

## 目标

- 增加 /workspaces/:wid 路由与空间选择页。
- 切换空间时隔离 query cache 和页面状态。
- 旧路由按最近且有权限的空间重定向。

## 设计依据

- [03 §5–§7](../../../plans/fullstack-design/03-frontend-architecture.md)：启动、路由和状态。
- [08 §1.4、§4.2](../../../plans/fullstack-design/08-frontend-implementation.md)：重定向与空间壳。

## 实现内容

- bootstrap 只依赖 auth/session。
- queryKeys 以 workspaceId 开头。
- TopNav 增加空间切换器和用户菜单。
- 产出检视记录与集成冒烟报告，落在 plans/ 与 reports/；启动改走 auth/session 后跨栈集成测试需初始化外部表，故 scope 覆盖 tests/integration。

## 实施步骤

1. 先写路由守卫和缓存失效测试。
2. 实现空间壳与旧路由适配。
3. 补 E2E 导航和跨空间切换。

## 依赖与交付边界

- 依赖：m7-04、m7-06、m7-07
- 交付边界：不实现空间管理四 Tab。

## 独立验证

```sh
pnpm test:web; pnpm typecheck:web; pnpm test:e2e -- --pattern workspace-shell
```

- 未登录进入空间路由跳登录。
- 无权限空间跳选择页。
- 切空间后旧 query 不命中。

## 验收标准

- 所有业务页面都带 wid。
- 旧深链只重定向一次。

## 门禁与 CI

- Web 单测、类型、E2E 与 flow 门禁。

## 非目标

- 不重做 V1 页面视觉。
- 不保留全局 query cache。
