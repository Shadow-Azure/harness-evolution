# m3-02 Graph Layout Core

English | [中文](m3-02-graph-layout-core.md)

```yaml flow
kind: issue
id: m3-02
milestone: m3
depends:
  - m3-01
priority: P0
status: backlog
scope:
  - apps/web/**
  - packages/contracts/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr:
adr: []
github:
  number: 42
  url: https://github.com/Shadow-Azure/harness-evolution/issues/42
```

## Background





m3-02 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## Goals





- 完成 m3-02 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## Design authority





- [03 §8.3 React Flow 迁移](../../../plans/fullstack-design/03-frontend-architecture.md)
- [08 §3 布局核心](../../../plans/fullstack-design/08-frontend-implementation.md)
- [09 R1 风险](../../../plans/fullstack-design/README.md)

## Implementation





- 将 chainOf/buildGraph/锚点/折叠几何移植为纯 TS
- 先支持 demo-nested 四项验收
- 节点坐标不依赖 DOM

## Implementation steps





1. 写归属、嵌套、折叠、边不交叉的失败测试
2. 实现 layout.ts 和最小 AgentTree
3. 加视觉 fixture

## Dependencies and boundary





- 依赖：m3-01
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:api -- tests/m3-02-graph-layout-core
pnpm test:db
pnpm test:web
pnpm test:e2e
```

- 布局测试通过
- demo-nested 归属/嵌套/折叠/连线全部正确

## Acceptance





- 纯函数可复现且无 DOM 副作用

## Gates and CI





- layout 单测、组件最小树测试

## Non-goals

- No scope creep beyond the listed non-goals and acceptance.
