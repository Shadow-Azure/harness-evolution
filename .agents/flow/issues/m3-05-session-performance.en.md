# m3-05 Session Performance

English | [中文](m3-05-session-performance.md)

```yaml flow
kind: issue
id: m3-05
milestone: m3
depends:
  - m3-04
priority: P1
status: in-progress
scope:
  - apps/web/**
  - scripts/**
  - tests/**
  - fixtures/**
  - package.json
  - .github/workflows/ci.yml
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
  - plans/**
  - reports/**
adr: []
github:
  number: 45
  url: https://github.com/Shadow-Azure/harness-evolution/issues/45
```

## Background





m3-05 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## Goals





- 完成 m3-05 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## Design authority





- [03 §10 性能门禁](../../../plans/fullstack-design/03-frontend-architecture.md)
- [08 §14 测试](../../../plans/fullstack-design/08-frontend-implementation.md)
- [07 性能策略](../../../plans/fullstack-design/README.md)

## Implementation





- 实现大树懒加载/按需数据、滚动恢复和交互预算
- 建立本地 4 会话性能报告和 CI bundle/build guard

## Implementation steps





1. 建立合成 61-Agent 大树和真实浏览器性能报告
2. 恢复每个 Session 的列表与概览滚动位置
3. 把 bundle 体积、懒加载、交互与长任务预算接入 CI

## Dependencies and boundary





- 依赖：m3-04
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:web -- session performance agent-tree
pnpm test:e2e --pattern "performance"
pnpm performance:report
pnpm build
pnpm verify:bundle
```

- entry 不超过 250KB raw / 90KB gzip，各 vendor 不超过 400KB
- 61-Agent 合成树展开不超过 350ms，长任务不超过 200ms
- 列表与概览按 Session 恢复滚动位置，刷新后重置

## Acceptance





- 打开树首屏可交互
- Vue Flow 只按需加载

## Gates and CI





- 性能 gate、bundle gate、E2E

## Non-goals

- No scope creep beyond the listed non-goals and acceptance.
