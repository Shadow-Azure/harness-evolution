# m5-03 Target Config Ui

English | [中文](m5-03-target-config-ui.md)

```yaml flow
kind: issue
id: m5-03
milestone: m5
depends:
  - m5-02
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
  number: 52
  url: https://github.com/Shadow-Azure/harness-evolution/issues/52
```

## Background





m5-03 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## Goals





- 完成 m5-03 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## Design authority





- [08 §9.5 配置页](../../../plans/fullstack-design/08-frontend-implementation.md)
- [08 §9.1 向导入口](../../../plans/fullstack-design/08-frontend-implementation.md)
- [02 §2.2 F19](../../../plans/fullstack-design/02-features.md)

## Implementation





- 实现对象配置列表/表单、启停、校验错误、删除确认和向导齿轮入口

## Implementation steps





1. 写表单校验、CRUD 错误和入口联动失败测试
2. 实现页面与 query 失效
3. 接真实 API

## Dependencies and boundary





- 依赖：m5-02
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:api -- tests/m5-03-target-config-ui
pnpm test:db
pnpm test:web
pnpm test:e2e
```

- CI E2E 可创建/编辑/停用
- 无效 repo 显示服务端错误

## Acceptance





- 配置页与向导状态一致

## Gates and CI





- 组件测试、E2E、contract gate

## Non-goals

- No scope creep beyond the listed non-goals and acceptance.
