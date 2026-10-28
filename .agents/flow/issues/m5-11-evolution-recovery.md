# m5-11 evolution recovery

[English](m5-11-evolution-recovery.en.md) | 中文

```yaml flow
kind: issue
id: m5-11
milestone: m5
depends:
  - m5-10
priority: P0
status: done
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - fixtures/**
  - tests/e2e/**
  - plans/2026-10-28-pr*-review.md
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr:
  - ../../notes/implemented/architecture/2026-10-28-evolution-recovery.md
github:
  number: 60
  url: https://github.com/Shadow-Azure/harness-evolution/issues/60
```

## 背景

m5-11 是可独立合并的垂直切片；实现取舍必须以链接的 fullstack-design 章节为准，不能在 issue 中复制出第二套设计事实。

## 目标

- 完成 m5-11 声明的交付边界，并让它可通过下列命令独立验收。
- 保持 contracts、数据库、前端与既有门禁一致。
- 失败、空态和重复输入都有明确行为。

## 设计依据

- [07 §5.8.1 阻塞重试](../../../plans/fullstack-design/07-backend-implementation.md)
- [05 §4.14 SSE](../../../plans/fullstack-design/05-api-design.md)
- [06 §5.7 events](../../../plans/fullstack-design/06-database-design.md)

## 实现内容

- 实现 blocked_sweeper 1/5/15 分钟退避、retry 仅 blocked、进程恢复、SSE 运行联动和完整占位闭环冒烟

## 实施步骤

1. 写三次退避、不可重试错误、重启和断线补发失败测试
2. 实现 sweeper/retry
3. E2E 走完准备→候选→评测→接纳/拒绝

## 依赖与交付边界

- 依赖：m5-10
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## 独立验证

```sh
pnpm test:api -- tests/m5-11-evolution-recovery
pnpm test:db
pnpm test:web
pnpm test:e2e
```

- E2E run 自动结束且日志完整
- 断线重连恢复进度

## 验收标准

- 失败可恢复，run 分支和历史一致

## 门禁与 CI

- E2E full placeholder、sweeper tests、events replay

## 非目标

- 不接真实 patch/评测
