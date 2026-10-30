# Agent Note: bad_cases 目录数据定时同步

Status: implemented

[English](2026-10-30-bad-case-catalog-sync.en.md) | 中文

## Problem

`bad_cases` 原先被当作数据库里已经存在的数据：本服务只读，外部系统直写同库。上游改成独立分页查询接口后，问题列表、错误详情与根会话轨迹补齐都会因为没有数据来源而失效；m6-15 只补根会话轨迹，不负责 bad_cases 入库。

## Decision

新增 `bad_case_catalog_sync` 单行游标表与同名定时任务：启动时若上次已结束立即跑一次，之后按 interval 触发，任务单飞且串行。同步按 `bad_case_id` 游标分页，`offset` 固定 0、页大小 200；每页在单事务内 upsert 全部 items 并推进游标、`synced_count`、`pending_count`，失败整页回滚。冷启动游标从 0 开始，首轮全量重拉，已存在 id 更新全部上游字段。前端在“数据同步”浮层按问题数量 → 问题轨迹 → 会话归一化 → 归因分析展示；归因分析只读 `bad_case_analysis` 聚合，不实现归因流程。上游 `object_name` / `object_type` 为空时按写入映射降级：`object_name → source → unknown`、`object_type → skill`。

## Alternatives considered

- 按 offset 翻页：新写入会让后续页漂移，崩溃后也难以判断已消费位置；游标式每页独立可重入，失败后从最后提交页继续。
- 逐条 select-then-write：与外部写入方存在竞态；按方言使用 `ON CONFLICT DO UPDATE` / `ON DUPLICATE KEY UPDATE` 原子覆盖。
- 冷启动从本库最大 id 开始：省首轮调用，但“已存在则更新”不会在上线首轮发生；选择从 0 全量重拉，用页大小、最大页数与时间预算摊到多个 tick。
- 归因进度落物化列：问题侧数据随上游变化，物化必然陈旧；改为查询时两条 COUNT 聚合。
- 复用 `HE_SESSION_QUERY_*`：两个服务的令牌和版本可能不同；新增独立的 `HE_BAD_CASE_QUERY_*` 命名空间。

## Consequences

新增服务自有表、迁移、job kind、配置与三个状态块；`bad_cases` 从“仅外部写”变为“外部写与目录同步写并存、按主键幂等覆盖”，关联表保持只读。接口只返回 `id > cursor`，旧 id 的内容变更无法感知；上游删除不做墓碑同步。CI 不访问真实上游，联调与冒烟使用 mock 服务。
