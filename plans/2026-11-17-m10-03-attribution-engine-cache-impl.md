# m10-03 归因引擎、缓存与候选写入实现计划

> 面向未读过本仓库的执行者：按任务顺序做，每个任务先写失败测试再写实现。命令行在仓库根执行。

**目标：** 为 V2 自进化提供对象·revision 级归因：纯函数 `rule-v1` 引擎、按七元组缓存键复用/重算、候选与归因原子落库，以及 `blocked(attribution)` 可恢复语义。

**设计依据：** [07 §5.13](../plans/fullstack-design/07-backend-implementation.md)、[06 §4.2 与 §5.8](../plans/fullstack-design/06-database-design.md)、[04 §5.4](../plans/fullstack-design/04-backend-architecture.md)。

**技术栈：** Python 3.12、FastAPI、SQLAlchemy 2 async、Alembic、pytest/pytest-asyncio、SQLite 与 MySQL 双方言。

## 全局约束

- 现有表名、`probe_id` 兼容链、候选唯一键 `(run_id, bad_case_id)` 不变。
- 引擎不访问数据库；缓存、upsert、候选关联全部在 runner/repository。
- 缓存键固定为 `sha256(workspace_id + bad_case_id + probe_type + probe_object + object_version + policy_version + attribution_engine)`，`object_version` 分量使用解析后的 `targetRevision`。
- 同一缓存键并发写入必须走方言原子 upsert，不先查后写。
- `non_target` 的 `attribute_type` 为 NULL，保留 probe 与关联，但不进入可聚类集合。
- 归因失败抛 `RunBlocked(stage="attribution")`，已完成条目保持落库；重跑只补未完成条目。

## 文件结构

- `apps/api/alembic/versions/0021_attribution_run_snapshot.py`：新增 run 快照列、扩宽 `probe_reports.object_version`。
- `apps/api/app/db/models/domain.py`、`evolution.py`：同步表模型与 `EvolutionRunRecord`。
- `apps/api/app/db/crud/attributions.py`：缓存命中读取、批次证据读取、probe+link+candidate 原子写入、可聚类 probe 查询。
- `apps/api/app/db/crud/evolution.py`：run 创建/读回新列。
- `apps/api/app/service/evolution/attribution.py`：`AttributionInput`、`AttributionResult`、引擎协议、`RuleBasedEngine`、注册表、`AttributionRunner`。
- `apps/api/app/service/evolution/engine/contracts.py`、`events.py`、`jobs.py`、`retry.py`、`runs.py`：接受 `attribution` blocked stage。
- `apps/api/tests/attribution/`：全部新增测试；必要时在 `apps/api/tests/test_database.py` 增加 MySQL 双方言用例。

## Task 1：模式演进

**文件**
- 新建 `apps/api/alembic/versions/0021_attribution_run_snapshot.py`
- 修改 `apps/api/app/db/models/domain.py`（`probe_reports.object_version` → 96）
- 修改 `apps/api/app/db/models/evolution.py`（`evolution_runs` 三列 + `EvolutionRunRecord` 三字段）
- 测试 `apps/api/tests/attribution/test_attribution_migration.py`

**步骤**
1. 写失败测试：升级 0020 后升级到 head，断言 `probe_reports.object_version` 长度 ≥96、`evolution_runs` 有 `potential_policy/cache_enabled/attribution_engine`，旧行取默认值；重复 `upgrade` 不报错。
2. 跑测试确认失败。
3. 实现 0021：按表/列存在性守卫；SQLite 用 batch，MySQL 用 `alter_column`；`attribution_engine` 默认 `legacy-probe-import`，`cache_enabled` 默认 `false`。
4. 同步模型与 record 默认值。
5. 跑测试通过。

## Task 2：repository 缓存与原子关联

**文件**
- 修改 `apps/api/app/db/crud/attributions.py`
- 测试 `apps/api/tests/attribution/test_attribution_repository.py`

**步骤**
1. 写失败测试：`get_probe_by_cache_key` 命中/未命中；`write_probe_and_link` 在同事务写 probe、`bad_case_analysis`、候选 `probe_id/is_cached=false`，候选缺失时三表全部回滚；`reuse_probe_and_link` 递增 `reused_count` 且同 run 只计一次，候选 `is_cached=true`；`linked_probe_ids` 与 `list_clusterable_probe_ids` 排除 `non_target`。
2. 跑测试确认失败。
3. 实现数据类 `ProbeCacheRecord`、`BadCaseEvidenceRecord`、`KnowledgeEvidenceRecord` 与上述方法；复用现有方言 upsert 辅助。
4. 跑测试通过。
5. 在 `apps/api/tests/test_database.py` 增加同一原子写入的 MySQL 用例（`@pytest.mark.mysql`）。

## Task 3：rule-v1 引擎与注册表

**文件**
- 新建 `apps/api/app/service/evolution/attribution.py`
- 测试 `apps/api/tests/attribution/test_rule_engine.py`、`test_registry.py`

**步骤**
1. 写失败测试：自身上报有 `metaData.error` → `attributed/error/0.8`；自身上报无错误证据 → `attributed/prompt/0.8`；`after_object` + discovery → `attributed/error/0.6`；证据不足/顺序不可比 → `non_target/None/0.7`；knowledge 证据进入 `reasoning` 且无错误证据时 category 为 prompt；相同输入两次输出逐字相同；注册表未知 key 抛 `ConfigError`。
2. 跑测试确认失败。
3. 实现 `AttributionInput`、`AttributionResult`、`AttributionEngine` Protocol、`RuleBasedEngine`、`resolve_attribution_engine`。
4. 跑测试通过。

## Task 4：runner

**文件**
- 修改 `apps/api/app/service/evolution/attribution.py`
- 测试 `apps/api/tests/attribution/test_attribution_runner.py`

**步骤**
1. 写失败测试：首次 run 为每个 included 候选写 probe+link+candidate；第二次同 run 走缓存，`reused_count` 每 run 只加一次且候选 `is_cached=true`；`cache_enabled=false` 时重算并覆盖同键行、`created_run_id` 更新、`reused_count` 不清零；引擎第二次调用抛错时首个候选已落库并抛 `RunBlocked(stage="attribution")`，重跑只处理剩余候选、首个候选 `updated_at` 不变；`non_target` 保留且不出现在 `list_clusterable_probe_ids`；knowledge 证据写进 reasoning；并发两个 run 同键收敛到一行 probe。
2. 跑测试确认失败。
3. 实现 runner：按 `run.attribution_engine` 解析引擎、`resolve_target_revision(run.target_version)` 作为版本分量、批次加载坏例与 knowledge 证据、逐条缓存读/写、异常包装为 `RunBlocked`、返回 `AttributionRunSummary`。
4. 跑测试通过。

## Task 5：blocked(attribution) 类型面

**文件**
- 修改 `apps/api/app/service/evolution/engine/contracts.py`
- 修改 `apps/api/app/service/evolution/events.py`
- 修改 `apps/api/app/service/jobs.py`
- 修改 `apps/api/app/service/evolution/retry.py`
- 修改 `apps/api/app/service/evolution/runs.py`
- 重新生成 `packages/contracts/openapi.json` 与 `src/generated/api.d.ts`
- 测试 `apps/api/tests/attribution/test_blocked_attribution.py`

**步骤**
1. 写失败测试：`RunBlocked(stage="attribution")` 可被 jobs 的 blocked 映射与事件记录接受；run detail schema 接受 `blockedStage=attribution`；retry 阶段映射接受 attribution。
2. 跑测试确认失败。
3. 扩展类型与映射；不实现 m10-04 的 prepare 阶段重入，只保证基础设施不拒绝该值。
4. `pnpm contract:generate`，跑测试通过。

## Task 6：文档与门禁

**文件**
- 新建 `.agents/notes/implemented/architecture/2026-11-17-attribution-engine-cache.md` 与 `.en.md`、`.i18n.yaml`
- 更新 `.agents/flow/issues/m10-03-attribution-engine-cache.md` / `.en.md` / `.i18n.yaml` 的 status 与 scope

**步骤**
1. 写 Note：Problem / Decision / Alternatives considered / Consequences；解释缓存键、原子写入、non_target、blocked 恢复。
2. 扩 scope：`apps/api/app/db/**`、`apps/api/alembic/**`、`apps/api/app/service/jobs.py`、`apps/api/tests/**`、`plans/**` 等实际改动面。
3. 跑 `pnpm record:i18n` 对应三件套。
4. 跑 `pnpm verify:flow`、`pnpm lint:docs`。

## 完成判定

- `pnpm test:api -- tests/attribution` 全绿。
- `pnpm test:db` 与 `pnpm test:db:mysql` 全绿（本地 MySQL 容器）。
- `pnpm lint:api`、`pnpm typecheck:api`、`pnpm contract:check`、`pnpm verify:flow`、`pnpm lint:docs` 全绿。
- PR 描述记录：无 UI 变更，因此无前后端 UI 对比；附 API/DB 集成验证与 CI 事实。
