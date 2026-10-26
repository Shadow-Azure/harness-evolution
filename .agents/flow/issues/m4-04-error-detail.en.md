# m4-04 Error Detail

English | [中文](m4-04-error-detail.md)

```yaml flow
kind: issue
id: m4-04
milestone: m4
depends:
  - m4-03
priority: P0
status: done
scope:
  - apps/web/**
  - packages/contracts/**
  - fixtures/**
  - tests/**
  - pnpm-lock.yaml
  - plans/**
  - reports/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 49
  url: https://github.com/Shadow-Azure/harness-evolution/issues/49
```

## Background





m4-04 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## Goals





- 完成 m4-04 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## Design authority





- [03 §6 路由](../../../plans/fullstack-design/03-frontend-architecture.md)
- [08 §7 错误详情](../../../plans/fullstack-design/08-frontend-implementation.md)
- [09 追溯矩阵](../../../plans/fullstack-design/README.md)

## Implementation





- 实现错误详情三栏、执行流过滤、归因双 Tab、 metaData 展示、全部错误恢复和深链刷新

## Implementation steps





1. 先写五态、tab 顺序、刷新恢复和错误空态失败测试
2. 实现页面与联动
3. 做 CI E2E 和本地对照

## Dependencies and boundary





- 依赖：m4-03
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:api -- tests/m4-04-error-detail
pnpm test:db
pnpm test:web
pnpm test:e2e
```

- CI E2E 五态通过
- 本地错误详情与 fixture 状态一致

## Acceptance





- 刷新后选中错误、tab 和过滤恢复
- 异常字段有降级

## Gates and CI





- 页面 E2E、组件测试、contract gate

## Non-goals

- No scope creep beyond the listed non-goals and acceptance.
