# Agent Note: 多归因、缓存与候选快照

Status: implemented

[English](2026-11-17-multi-attribution-schema.en.md) | 中文

## Problem

V1 的 `bad_case_analysis` 用 `UNIQUE(bad_case_id)` 把归因压成 1:1 状态行；V2 要让一个 case 对不同对象和版本有多条归因，同时保留历史 probe 读取链和既有表名。`probe_reports` 只有对象明细，没有空间、结论、缓存与复用字段，run 也无法解释“哪些 case 进或没进潜在、走了缓存没有”。若新建平行归因表，`probe_id` 兼容链会断裂；若把历史 `nonissue`、空 `probe_id` 强行清洗成 NOT NULL 语义，就会删除或伪造 V1 行。

## Decision

- 原位演进：删 `uq_bad_case_analysis_case`，加 `UNIQUE(bad_case_id, probe_id)`；`analysis_status` 可空，V2 新行不写 `analysis_status`/`analysis_result`，结论以 `probe_reports.conclusion` 为唯一真相。`probe_id` 与 `cache_key` 保持可空：V1 `unanalyzed`/`analyzed_nonissue` 行可能没有 probe，孤立 probe 也算不出缓存键；V2 repository 写入时强制非空。该例外记入 06 §4.2/§9，M11 兼容退役时再收紧。`object_version` 继续可空，历史空值不回填伪版本。
- 缓存键固定为 `sha256(workspace_id + bad_case_id + probe_type + probe_object + object_version + policy_version + attribution_engine)`，字段顺序固定、缺失版本用空串。workspace 与 case 都在键里，避免跨空间或跨 case 冲突；`probe_id` 仍是稳定归因 ID，命中时复用。
- 同键写入用方言原子语句：SQLite `on_conflict_do_update(index_elements=[cache_key])`、MySQL `on_duplicate_key_update`；不先查后写。冲突时保留原 `probe_id`/`created_at`，刷新结论、描述、引擎、`created_run_id` 与 `updated_at`。缓存命中走 `reuse()` 只加 `reused_count`、写 `last_reused_run_id` 与 `updated_at`，不另插行。
- `evolution_run_candidates` 全量保存：`included=false` 的排除行也落库，携带两个触发点坐标、`order_state`、`included_reason`、`probe_id` 与 `is_cached`；`UNIQUE(run_id, bad_case_id)` 让重跑 prepare 幂等。簇成员仍由 `probe_cluster_probes` 推导，不另建候选与簇的关联表。
- 迁移 `0020` 排在 `0019` 之后，SQLite 用 batch、MySQL 用 ALTER；列、索引、外键逐项按存在性判定，重复 upgrade 与半途 DDL 重试都只补缺失项。`bad_case_analysis`/`probe_reports` 缺失时跳过对应演进；`bad_cases` 缺失时候选表仍创建但不加该外键。回填只更新 NULL 或默认值：workspace 取关联 case 的空间，conclusion 取最新 `analysis_status` 映射，`nonissue` 或空串的 `attribute_type` 置 NULL，cache key 用 Python 重算（SQLite 无 sha256），孤立 probe 留 NULL。
- 外键由迁移独占：`probe_reports` 的空间与 run 列、候选表的空间与问题列在 ORM 表定义里保持普通字符串，因为 `ensure_fixture_external_tables` 只带问题侧 metadata 建表，声明跨 metadata 外键会让外部表 bootstrap 在 `create_all` 排序时失败；schema 事实以迁移为准。
- 兼容读取：`get_analysis` 由 `one_or_none()` 改为按 `updated_at DESC, id DESC LIMIT 1`，一 case 多行不再 `MultipleResultsFound`；快照与批量分析按 case、时间、id 稳定排序，V1 API 仍只展示最新兼容行，多归因展示留给 m11-01。

## Alternatives considered

- **新建 V2 归因表**：会切断 `probe_id` 与 `/api/probes/*`、`probe_cluster_probes` 的兼容链，且两套 ID 并存；拒绝。
- **把 `probe_id`/`cache_key` 收紧 NOT NULL 并删历史行**：生产无数据，但 fixtures 与开发库有 V1 `unanalyzed` 行，删除或补假 probe 都会改变历史语义；拒绝，保留 NULL 例外。
- **在应用层先查 `cache_key` 再插入或更新**：并发下会撞唯一键或产生重复 probe；拒绝，用方言原子 upsert。
- **只保存 `included=true` 候选**：运行详情无法解释“为什么没进潜在”，也无法还原策略排除；拒绝，全量保存。
- **用 SQL `SHA2` 或自定义函数回填 cache key**：SQLite 无 `sha256` 内建函数，双方言无法共用；拒绝，迁移内用 Python 逐行重算。
- **在 ORM 表上声明所有外键**：跨 metadata 的外键会让 `ensure_fixture_external_tables` 的 `create_all` 失败；拒绝，外键只放在迁移。
- **用新表存候选与簇的关联**：候选已是 run 级事实，簇成员是它的子集，重复表会两处不一致；拒绝，见 06 §5.10。

## Consequences

- 一 case 多归因成为常态；旧读端点取最新行，展示全部归因由 m11-01 接管。
- 同 cache key 的并发 upsert 收敛到同一 `probe_id`；`reused_count` 是缓存命中的审计计数，不表示 run 数。
- 历史 V1 行保留 `analysis_status`/`analysis_result`；V2 行的这两列为 NULL，legacy 读接口会按空状态降级。
- 孤立历史 probe 的 `cache_key` 永远为 NULL，无法命中缓存；它们仍可被旧 probe 读端点读取。
- 迁移可重试、可降级；降级前会把一 case 多行裁到最新一行、把 V2 NULL 状态映射回 `analyzed_*`，因此降级不是无损回放，生产回滚以“回退应用版本 + 保留新结构”为主。
- 候选表随 run 级联删除；空间删除级联仍有外键保护（MySQL 与 SQLite 建表时声明）。
- 无 API、service 与前端改动：新列与新表暂不被旧端点暴露。
