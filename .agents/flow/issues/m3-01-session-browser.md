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
status: backlog
scope:
  - apps/web/**
  - packages/contracts/**
  - fixtures/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 41
  url: https://github.com/Shadow-Azure/harness-evolution/issues/41
```

## 背景

m3-01 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## 目标

- 完成 m3-01 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## 设计依据

- [03 §5 Session 浏览器](../../../plans/fullstack-design/03-frontend-architecture.md)
- [08 §5 组件树](../../../plans/fullstack-design/08-frontend-implementation.md)
- [02 §2.1 F3/F4](../../../plans/fullstack-design/02-features.md)

## 实现内容

- 实现列表卡、概览、同步状态、搜索筛选排序、空/加载/失败态和 URL 恢复
- 问题数显示 0

## 实施步骤

1. 先用 MSW 和 seed 写组件/E2E 失败测试
2. 实现 SessionCard/Overview/query
3. 接真实 API 并做本地 4 会话检查

## 依赖与交付边界

- 依赖：m2-06, m2-07
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## 独立验证

```sh
pnpm test:api -- tests/m3-01-session-browser
pnpm test:db
pnpm test:web
pnpm test:e2e
```

- CI seed E2E 通过
- 本地会话列表和概览与 API 统计一致

## 验收标准

- 刷新后搜索、排序、选中 session 恢复
- 三态可重试

## 门禁与 CI

- 组件测试、query gate、Playwright 冒烟

## 非目标

- 不画执行流图
