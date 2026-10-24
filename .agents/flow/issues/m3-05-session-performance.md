# m3-05 session performance

[English](m3-05-session-performance.en.md) | 中文

```yaml flow
kind: issue
id: m3-05
milestone: m3
depends:
  - m3-04
priority: P1
status: backlog
scope:
  - apps/web/**
  - scripts/**
  - fixtures/**
  - .github/workflows/ci.yml
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr:
adr: []
github:
  number: 45
  url: https://github.com/Shadow-Azure/harness-evolution/issues/45
```

## 背景

m3-05 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## 目标

- 完成 m3-05 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## 设计依据

- [03 §10 性能门禁](../../../plans/fullstack-design/03-frontend-architecture.md)
- [08 §14 测试](../../../plans/fullstack-design/08-frontend-implementation.md)
- [07 性能策略](../../../plans/fullstack-design/README.md)

## 实现内容

- 实现大树懒加载/按需数据、滚动恢复和交互预算
- 建立本地 4 会话性能报告和 CI bundle/build guard

## 实施步骤

1. 用最大本地树测量 TTI、交互延迟和滚动
2. 优化组件拆分与缓存
3. 把体积和首屏依赖检查接入 CI

## 依赖与交付边界

- 依赖：m3-04
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## 独立验证

```sh
pnpm test:api -- tests/m3-05-session-performance
pnpm test:db
pnpm test:web
pnpm test:e2e
```

- 本地最大会话滚动不卡死
- CI verify:bundle/build guard 通过

## 验收标准

- 打开树首屏可交互
- Vue Flow 只按需加载

## 门禁与 CI

- 性能 gate、bundle gate、E2E

## 非目标

- 不做像素级视觉回归
