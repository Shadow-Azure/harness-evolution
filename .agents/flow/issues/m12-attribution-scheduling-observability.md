# 归因任务调度、重试与运行观测

[English](m12-attribution-scheduling-observability.en.md) | 中文

```yaml flow
kind: issue
id: m12-22
milestone: m12
depends:
  - m12-19
  - m12-20
priority: P1
status: done
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - docs/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 318
  url: https://github.com/Shadow-Azure/harness-evolution/issues/318
```

## 背景

内网现有归因通过定时任务批量处理上报 Badcase，而仓库当前只在自进化 Run prepare 中串行调用归因引擎。真实 Agent 调用可能持续数十秒并产生重试、Token 和限流；若继续占用全局串行 worker，归因会阻塞同步与其他 Run，手工启动、定时任务和失败恢复也可能形成三套执行语义。

## 目标

- 让用户启动、定时任务和失败重试复用同一归因服务与执行清单。
- 支持 Session 级上下文复用、Badcase 级有界并发、幂等 claim 和可恢复状态。
- 提供运行量、缓存、延迟、Token、错误和证据覆盖观测。

## 设计依据

- [04 §7.2、§8](../../../plans/fullstack-design/04-backend-architecture.md)：任务真值、串行 worker 与扩展路径。
- [07 §5.11–5.13](../../../plans/fullstack-design/07-backend-implementation.md)：prepare、归因 Runner 与事件。
- [06 §5.8–5.9](../../../plans/fullstack-design/06-database-design.md)：归因缓存和候选快照。

## 实现内容

- 在 `job_runs`/执行记录上实现持久化 claim、租约、超时、重试、取消和并发上限。
- 同一 Session 先组装一次上下文，再对其 Badcases 有界并发；不同入口共享幂等键和缓存。
- 评审并选择 `attribution_only` Run mode 或复用 `cluster_only`，只保留一个正式定时入口。
- 记录 executor、Skill/model revision、上下文 hash、耗时、Token、重试、缓存与 warning 指标。
- 对外提供进度、失败原因和单条重试；日志和指标不包含原始 Trace、Skill 正文或密钥。

## 实施步骤

1. 写重复调度、worker 重启、租约过期、部分成功和限流测试。
2. 实现持久化执行队列与 Session 批次编排。
3. 接手工、定时和 retry 入口及进度读取。
4. 增加指标、告警、脱敏和运维文档。

## 依赖与交付边界

- 依赖：m12-19、m12-20。
- 交付边界：生产化调度与观测已验证的归因引擎；不改变归因算法和质量晋级结论。

## 独立验证

```sh
pnpm test:api -- tests/attribution_jobs
pnpm test:db
pnpm test:db:mysql
pnpm test:e2e -- --pattern attribution-jobs
```

- 重复触发只产生一次有效执行，进程重启后可从持久化状态恢复。
- 一个 Badcase 失败不覆盖同 Session 已完成报告，重试只处理未完成项。

## 验收标准

- 手工、定时和 Run prepare 对同一执行清单共享缓存和幂等语义。
- LLM 慢调用不会长期持有当前全局 worker 锁或阻塞轨迹同步。
- 管理员可查看吞吐、失败、延迟、Token、缓存和 warning，且无敏感内容泄露。

## 门禁与 CI

- API、双库、重启恢复、并发、E2E、脱敏、文档与 Flow 门禁。

## 非目标

- 不引入第二套归因报告、第二套缓存或入口特有算法。
- 不提供无限并发、无限自动重试或自动晋级未通过质量门禁的 Skill。
