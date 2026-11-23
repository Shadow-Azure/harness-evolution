# 归因模块：通过 .env 限制 attribute 落盘记录数，超限清理最早记录

[English](bugfix-attribution-disk-retention.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-29
milestone: bugfix
depends: []
priority: P1
status: backlog
scope:
  - apps/api/**
  - attribute/README*
  - deploy/env.production.example
  - .agents/flow/issues/bugfix-attribution-disk-retention*
  - .agents/notes/**
adr: []
github:
  number: 532
  url: https://github.com/Shadow-Azure/harness-evolution/issues/532
```

## 背景

后台对象绑定和向导关闭缓存重算都会在 `attribute/<workspace>/` 写入逐 Badcase 输入、执行日志和报告副本。Session 证据、对象原文和归因 Skill 快照可由多个批次共享。长期运行时落盘记录持续增加，会占用服务器磁盘；仅复用数据库报告无法限制磁盘增长。关联 #387、#417。

## 目标

通过部署端 `.env` 设置每个工作空间的落盘记录数量上限。超过上限时，按完成时间从早到晚自动回收，优先保留最近的归因记录。

## 设计依据

沿用归因报告与候选的数据库缓存语义，以及后台批次和向导 Run 的输入归档方式。[后端设计 §5.13 归因生成与缓存](../../../plans/fullstack-design/07-backend-implementation.md#513-归因生成与缓存serviceevolutionattributionpy)

## 实现内容

- 建议配置名为 `HE_ATTRIBUTION_CACHE_MAX_RECORDS`。默认采用文档化的有限正整数，部署可覆盖；零、负数和无效值在启动时给出配置错误。
- 一个空间内，以 `(batch_id, badcase_id)` 计一条落盘记录。一次重试归入同一条，新 Run 重算另计一条，纯数据库缓存命中不增加计数。按持久化完成时间排序，相同时间按稳定标识排序。
- 批次完成后触发检查，服务重启时也能补清积压。超限时只清理回到上限所需的最老记录，成组回收逐例输入、执行日志及输出副本。正在执行、排队或仍需原输入重试的记录受保护；暂时可清理的记录不足时，记录原因并在后续检查继续收敛。
- 共享 Session 证据、对象原文和 Skill 快照须在当前空间最后一个有效引用释放后才回收。当前对象绑定、已上传的 Skill 包及平台默认包保持可用。数据库报告、候选关联和向导缓存复用结果继续保留；按历史报告追溯已回收的磁盘详情时能明确识别归档已清理。

## 实施步骤

先统一计数、完成时间及受保护引用的获取方式，再接入按空间串行或等效的并发控制。记录清理前后数量、回收条数及跳过原因，支持任务中断后幂等重试，并在归因目录说明和部署环境示例中写明配置口径。

## 依赖与交付边界

覆盖本地 SQLite 和生产 MySQL 共用的文件归档路径。清理范围限定在目标工作空间，能与后台绑定归因、向导重算及既有缓存读取并行工作。

## 独立验证

新增合成回归，用 `pnpm test:api -- tests/attribution -k retention` 运行。设置上限为 3，在同一空间生成 5 条按完成时间可区分的记录，其中最早一条与最新一条共享同一份 Session 证据；在另一空间保留对照数据。

## 验收标准

1. 上限为 3 时，从 3 增至 4 后自动清掉最早 1 条。已有 5 条时回收到最新 3 条。将上限从 3 调为 2 并重启后，只再回收最早 1 条。
2. 两空间分别计数。重试和缓存命中符合计数约定。存在活动任务时，其冻结输入始终可读；保护解除后能回到上限。
3. 清理后仍可查询并复用旧数据库报告，最近记录保留的共享证据可以通过校验。与新归因并发或在清理中途重启，也不会误删其他空间、当前绑定、上传包或保留记录依赖的文件。

## 门禁与 CI

将数量阈值、清理顺序、共享引用和中断重试的用例纳入 API CI，运行 `pnpm lint:api`、`pnpm typecheck:api` 及相关 SQLite/MySQL 测试。

## 非目标

删除数据库历史报告、按保留天数替代数量上限、增加前端清理页面均不在本项范围内。
