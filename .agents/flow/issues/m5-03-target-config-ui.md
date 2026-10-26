# m5-03 target config ui

[English](m5-03-target-config-ui.en.md) | 中文

```yaml flow
kind: issue
id: m5-03
milestone: m5
depends:
  - m5-02
priority: P0
status: in-progress
scope:
  - apps/web/**
  - packages/contracts/**
  - fixtures/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 52
  url: https://github.com/Shadow-Azure/harness-evolution/issues/52
```

## 背景

m5-03 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## 目标

- 完成 m5-03 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## 设计依据

- [08 §9.5 配置页](../../../plans/fullstack-design/08-frontend-implementation.md)
- [08 §9.1 向导入口](../../../plans/fullstack-design/08-frontend-implementation.md)
- [02 §2.2 F19](../../../plans/fullstack-design/02-features.md)

## 实现内容

- 实现对象配置列表/表单、启停、校验错误、删除确认和向导齿轮入口

## 实施步骤

1. 写表单校验、CRUD 错误和入口联动失败测试
2. 实现页面与 query 失效
3. 接真实 API

## 依赖与交付边界

- 依赖：m5-02
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## 独立验证

```sh
pnpm test:api -- tests/m5-03-target-config-ui
pnpm test:db
pnpm test:web
pnpm test:e2e
```

- CI E2E 可创建/编辑/停用
- 无效 repo 显示服务端错误

## 验收标准

- 配置页与向导状态一致

## 门禁与 CI

- 组件测试、E2E、contract gate

## 非目标

- 不做权限分级
