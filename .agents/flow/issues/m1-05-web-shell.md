# Vue 3 应用骨架与前端质量门禁

[English](m1-05-web-shell.en.md) | 中文

```yaml flow
kind: issue
id: m1-05
milestone: m1
depends:
  - m1-04
priority: P0
status: backlog
scope:
  - apps/web/**
  - packages/contracts/**
  - package.json
  - pnpm-lock.yaml
  - scripts/**
  - .github/workflows/ci.yml
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 28
  url: https://github.com/Shadow-Azure/harness-evolution/issues/28
```

## 背景

原型交互需要 Vue Flow、Pinia/Query 和统一 tokens；先建立正确骨架可避免后续页面返工。

## 目标

- 用 Vue 3、router、pinia、@tanstack/query 和设计 tokens 重建 apps/web。
- 建立 node/jsdom Vitest、ESLint、vue-tsc、bundle 预算和构建守卫。
- 两个空视图可导航且契约类型可编译。

## 设计依据

- [04 后端架构](../../../plans/fullstack-design/04-backend-architecture.md)

## 实现内容

- 路由懒加载非默认页；Vue Flow 不进入首屏闭包。
- tokens.css 成唯一颜色源，禁止组件硬编码色值。
- MSW 只用于测试，运行时不留 mock 分支。

## 实施步骤

1. 先写路由、tokens、健康 API 调用和 bundle 守卫失败测试。
2. 创建 App/TopNav/router/query/http 骨架并删除 React。
3. 接入 lint/type/test/build 和 verify:bundle。

## 依赖与交付边界

- 依赖：m1-04
- 交付边界：只交付可导航空壳和公共数据层；不含登录与领域页面。

## 独立验证

```sh
pnpm test:web
pnpm typecheck:web
pnpm build
pnpm verify:bundle
```

- 首屏包不含 Vue Flow；bundle 超预算时构建后门禁失败。
- 组件和 API 测试均通过。

## 验收标准

- `pnpm dev:web` 可打开空态导航。
- React 文件被移除且构建成功。

## 门禁与 CI

- 前端 lint/type/test/build/bundle 进入 CI。

## 非目标

- 不实现登录、Session、图或进化页面。
