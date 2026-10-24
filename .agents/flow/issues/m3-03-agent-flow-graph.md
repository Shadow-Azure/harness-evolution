# m3-03 agent flow graph

[English](m3-03-agent-flow-graph.en.md) | 中文

```yaml flow
kind: issue
id: m3-03
milestone: m3
depends:
  - m3-02
priority: P0
status: backlog
scope:
  - apps/web/**
  - packages/contracts/**
  - fixtures/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr:
adr: []
github:
  number: 43
  url: https://github.com/Shadow-Azure/harness-evolution/issues/43
```

## 背景

m3-03 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## 目标

- 完成 m3-03 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## 设计依据

- [03 §8.3 Vue Flow](../../../plans/fullstack-design/03-frontend-architecture.md)
- [08 §3.3–3.4](../../../plans/fullstack-design/08-frontend-implementation.md)
- [02 §2.1 F5](../../../plans/fullstack-design/02-features.md)

## 实现内容

- 用 Vue Flow 渲染完整 Agent 树，支持 fitView、折叠、缩放、定位和键盘焦点
- 保持 vendor 懒加载

## 实施步骤

1. 实现组件、handle/边映射和可访问性
2. 用 CI fixtures 做交互测试
3. 本地最大树人工/截图验收

## 依赖与交付边界

- 依赖：m3-02
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## 独立验证

```sh
pnpm test:api -- tests/m3-03-agent-flow-graph
pnpm test:db
pnpm test:web
pnpm test:e2e
```

- 4 个本地会话树可浏览
- CI nested fixture E2E 通过
- 首屏闭包不含 Vue Flow

## 验收标准

- 大图可折叠、定位稳定且不穿边

## 门禁与 CI

- bundle build guard、E2E、组件测试

## 非目标

- 不做红色问题卡
