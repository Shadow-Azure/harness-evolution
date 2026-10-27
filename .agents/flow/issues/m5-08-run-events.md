# m5-08 run events

[English](m5-08-run-events.en.md) | 中文

```yaml flow
kind: issue
id: m5-08
milestone: m5
depends:
  - m5-01
  - m5-07
priority: P0
status: in-progress
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - fixtures/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
  - tests/e2e/**
  - tests/integration/**
adr:
  - ../../notes/implemented/architecture/2026-10-28-evolution-run-events.md
github:
  number: 57
  url: https://github.com/Shadow-Azure/harness-evolution/issues/57
```

## 背景

m5-08 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## 目标

- 完成 m5-08 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## 设计依据

- [05 §4.15 执行日志](../../../plans/fullstack-design/05-api-design.md)
- [06 §5.7 events](../../../plans/fullstack-design/06-database-design.md)
- [07 §5.9](../../../plans/fullstack-design/07-backend-implementation.md)

## 实现内容

- 实现 evolution_run_events 追加、events API、阶段/候选/push/eval/blocked/retry 事件和日志面板
- 错误脱敏 8KB

## 实施步骤

1. 写事件持久化、重启回放、脱敏和截断失败测试
2. 实现 service/API/panel

## 依赖与交付边界

- 依赖：m5-01, m5-07
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## 独立验证

```sh
pnpm test:api -- tests/m5-08-run-events
pnpm test:db
pnpm test:web
pnpm test:e2e
pnpm contract:check
```

- 刷新后事件顺序完整
- 密钥样例被替换
- 超长 detail 截断

## 验收标准

- 失败原因可在 UI 直接定位

## 门禁与 CI

- events gate、安全脱敏测试、E2E

## 非目标

- 不把原始 stderr 直接入库
