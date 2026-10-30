# m6-16 bad_cases 目录同步 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 bad_cases 从上游分页查询接口定时增量同步进本库，按主键 upsert，并在顶栏“数据同步”浮层按四段展示问题数量、问题轨迹、会话归一化与归因分析。

**Architecture:** 分页客户端（`third_party_api/bad_case_query`）严格解析上游响应；同步服务按游标逐页拉取，一页一事务 upsert + 推进单行状态表；coordinator 复用 `JobRunner` 单飞调度并在启动时立即跑一次；状态接口扩展三个统计块，前端 `TopNav` 浮层消费同一轮询。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2 async / Alembic / Pydantic v2 / httpx；Vue 3 + Vitest；SQLite + MySQL 双库。

**Spec:** `plans/fullstack-design/12-bad-case-catalog-sync.md`

## Global Constraints

- 冷启动游标从 0 开始，首轮全量重拉，已存在 `bad_case_id` 必须更新而非新增。
- `limit` 是 items 条数上限；客户端校验 `len(items) <= limit`，不依赖 `total - offset` 公式。
- 已同步数量 = `COUNT(bad_cases)`；页大小默认 200；时间戳缺失用同步时间兜底，不判非法。
- 任务单飞、串行；启动时若上次已结束立即执行一次，之后按 interval。
- 一页一事务；失败整页回滚、游标不前进。
- 浮层顺序固定：问题数量 → 问题轨迹 → 会话归一化 → 归因分析；空表不做特殊处理。
- CI 不访问真实上游；测试用 httpx.MockTransport 或 fake source。

## Review Focus

- 上游返回 `items` 数量超过 `limit`：必须拒绝整页并记 `BAD_CASE_QUERY_INVALID_RESPONSE`，不能截断后写库。
- 页内某条记录非法：整页回滚，游标与计数保持上一页的值，不产生半页数据。
- 已存在 id 的上游字段变化：必须覆盖 `title`/描述/时间戳，且不删除 `bad_case_analysis` 关联。
- `bad_cases` 表为空：浮层照常渲染四个 0 值段与 `问题轨迹 0/0`，不抛错、不隐藏。
- 上游未配置：目录同步段显示 `unavailable`，scheduler 不触发，不影响会话归一化与轨迹补齐。

---

### Task 1: 配置与错误码

**Files:**
- Modify: `apps/api/app/config.py`
- Modify: `apps/api/app/errors.py`
- Test: `apps/api/tests/m6-16-bad-case-catalog-sync/test_config.py`

**Interfaces:**
- Produces: `Settings.bad_case_query_base_url|token|timeout_seconds|retry_attempts|retry_backoff_seconds`，`bad_case_catalog_sync_interval_seconds|page_size|time_budget_seconds|max_pages`，`Settings.bad_case_query_configured -> bool`。
- Produces: `ErrorCode.BAD_CASE_QUERY_{UNAVAILABLE,UNAUTHORIZED,INVALID_RESPONSE,TIMEOUT,REQUEST_FAILED}`, `ErrorCode.BAD_CASE_CATALOG_SYNC_FAILED`, `ErrorCode.BAD_CASE_CATALOG_SYNC_INTERRUPTED`。

- [ ] **Step 1: 写失败测试** `test_config.py::test_catalog_sync_defaults_and_bounds`
  - 断言默认值：interval 300、page_size 200、time_budget 300、max_pages 100、timeout 30、retry 2、backoff 0.25。
  - 断言 `page_size=0`、`page_size=201`、`max_pages=0` 抛 `ValidationError`。
  - 断言 `bad_case_query_configured` 在 base_url/token 缺失时为 False。
- [ ] **Step 2: 运行并确认失败** `pnpm test:api -- tests/m6-16-bad-case-catalog-sync/test_config.py`
- [ ] **Step 3: 实现** 在 `Settings` 增加字段与 `bad_case_query_configured`；`bad_case_query_base_url` 复用 http/https、无凭据、无 query/fragment 的校验；错误码加到 `ErrorCode`。
- [ ] **Step 4: 运行通过** 同 Step 2。
- [ ] **Step 5: 提交** `git add apps/api/app/config.py apps/api/app/errors.py apps/api/tests/m6-16-bad-case-catalog-sync/test_config.py && git commit -m "feat(api): add catalog sync settings and error codes (#176)"`

### Task 2: 迁移与状态表模型

**Files:**
- Modify: `apps/api/app/db/models/domain.py`
- Create: `apps/api/alembic/versions/0012_bad_case_catalog_sync.py`
- Test: `apps/api/tests/m6-16-bad-case-catalog-sync/test_migration.py`

**Interfaces:**
- Produces: `bad_case_catalog_sync` Table，列 `id VARCHAR(16) PK`、`last_bad_case_id BIGINT`、`synced_count INTEGER`、`pending_count INTEGER`、`status VARCHAR(16)`、`attempts INTEGER`、`last_error TEXT NULL`、`last_run_at DATETIME NULL`、`last_success_at DATETIME NULL`、`updated_at DATETIME`。

- [ ] **Step 1: 写失败测试** `test_migration.py::test_upgrade_creates_catalog_sync_table`
  - 用 `create_database(Settings(db_dialect=SQLITE, data_dir=tmp_path, ...))` + `upgrade_database`，`inspect` 断言表与列存在、主键是 `id`。
- [ ] **Step 2: 运行失败** 同 Task 1 命令替换文件名。
- [ ] **Step 3: 实现** domain 增加表（`BigInteger().with_variant(Integer(), "sqlite")`）；alembic `0012` 建表。
- [ ] **Step 4: 运行通过** `pnpm test:api -- tests/m6-16-bad-case-catalog-sync/test_migration.py` 与 `pnpm test:db`。
- [ ] **Step 5: 提交** `git commit -m "feat(db): add bad_case_catalog_sync state table (#176)"`

### Task 3: 状态仓储、upsert 与归因统计

**Files:**
- Create: `apps/api/app/db/crud/bad_case_catalog_sync.py`
- Modify: `apps/api/app/db/crud/bad_cases.py`
- Test: `apps/api/tests/m6-16-bad-case-catalog-sync/test_catalog_sync_repository.py`

**Interfaces:**
- Produces: `CatalogSyncState(last_bad_case_id, synced_count, pending_count, status, attempts, last_error, last_run_at, last_success_at, updated_at)`。
- Produces: `BadCaseCatalogSyncRepository(database)` with `get_state()`, `initialize(now)`, `mark_running(now)`, `mark_failed(error, now)`, `mark_idle(now)`, `commit_page(items, last_bad_case_id, pending_count, now) -> UpsertCounts(inserted, updated)`, `count_bad_cases()`。
- Produces: `BadCaseRepository.analysis_progress() -> AnalysisProgress(total, analyzed, pending, issue, non_issue)`。
- `commit_page` 用方言 upsert：SQLite `on_conflict_do_update`，MySQL `on_duplicate_key_update`；同事务内写状态表并重算 `synced_count`。

- [ ] **Step 1: 写失败测试**
  - `test_state_initializes_at_cursor_zero`：无行时 `initialize` 后 cursor=0、status=idle、counts=0。
  - `test_commit_page_inserts_then_updates`：同一 id 提交两次，第二次返回 inserted=0、updated=1，行数仍为 1，`title`/`bad_case_description` 被覆盖，`bad_case_analysis` 行保留。
  - `test_commit_page_advances_cursor_and_counts`：两页后 cursor=最大 id、synced_count=行数、pending_count=上游剩余。
  - `test_analysis_progress_counts_statuses`：构造 analyzed_issue / analyzed_nonissue / unanalyzed / 无分析行，断言 total/analyzed/pending/issue/non_issue。
- [ ] **Step 2: 运行失败** 同 Task 1 命令替换文件名。
- [ ] **Step 3: 实现** 按 Interfaces 落仓储与统计；`commit_page` 先 `SELECT bad_case_id` 求 inserted/updated，再执行 upsert，最后更新状态行。
- [ ] **Step 4: 运行通过** 同 Step 2；再跑 `pnpm test:db`。
- [ ] **Step 5: 提交** `git commit -m "feat(db): add catalog sync repository and analysis counts (#176)"`

### Task 4: 上游分页客户端

**Files:**
- Create: `apps/api/app/third_party_api/bad_case_query/__init__.py`
- Create: `apps/api/app/third_party_api/bad_case_query/models.py`
- Create: `apps/api/app/third_party_api/bad_case_query/http.py`
- Test: `apps/api/tests/m6-16-bad-case-catalog-sync/test_bad_case_query_client.py`

**Interfaces:**
- Produces: `BadCaseItem`（`bad_case_id:int`、`bad_case_session_id`、`bad_case_type`、`object_name`、`object_type`、`object_version?`、`bad_case_agent_id?`、`title` alias `bad_case_title`、`description` alias `bad_case_description`、`meta_data?`、`source?`、`created_at?`、`updated_at?`）。
- Produces: `BadCasePage(total, offset, limit, items: tuple[BadCaseItem, ...])`。
- Produces: `BadCaseCatalogSource` Protocol `fetch_page(*, after_id: int, offset: int, limit: int) -> BadCasePage`、`close()`。
- Produces: `HttpBadCaseCatalogSource(client, *, max_retries=2, backoff_seconds=0.25, sleep=None)`。

- [ ] **Step 1: 写失败测试**（httpx.MockTransport）
  - `test_fetch_page_maps_title_and_optionals`：正常响应解析、`bad_case_title` → `title`、缺失时间戳为 None。
  - `test_fetch_page_rejects_oversized_and_unsorted_items`：`len(items) > limit`、id 非递增、`total < len(items)` 均抛 `BAD_CASE_QUERY_INVALID_RESPONSE`。
  - `test_fetch_page_rejects_missing_required_field` 与非法时间戳。
  - `test_fetch_page_maps_unauthorized`：401 → `BAD_CASE_QUERY_UNAUTHORIZED`。
  - `test_fetch_page_retries_5xx_then_fails`：两次 500 后 200，调用 3 次；持续 500 → `BAD_CASE_QUERY_REQUEST_FAILED`。
  - `test_calls_never_overlap`：并发两次 `fetch_page`，记录起止，断言区间不重叠。
- [ ] **Step 2: 运行失败**。
- [ ] **Step 3: 实现** Pydantic 模型（`extra="forbid"`, `populate_by_name=True`），httpx GET `bad-cases` 带 query 参数；重试 429/5xx/Timeout/TransportError；`asyncio.Lock` 包住请求。
- [ ] **Step 4: 运行通过**。
- [ ] **Step 5: 提交** `git commit -m "feat(api): add bad-case catalog query client (#176)"`

### Task 5: 同步服务

**Files:**
- Create: `apps/api/app/service/acquisition/bad_case_catalog_sync.py`
- Test: `apps/api/tests/m6-16-bad-case-catalog-sync/test_catalog_sync_service.py`

**Interfaces:**
- Produces: `KIND = "bad_case_catalog_sync"`。
- Produces: `CatalogSyncResult(pages, inserted, updated, last_bad_case_id, pending, exhausted)`。
- Produces: `BadCaseCatalogSyncService(repository, source, *, page_size=200, max_pages=100, time_budget_seconds=300.0, clock=now_shanghai)` with `from_settings(...)`、`handle(job) -> Mapping[str, Any]`、`run(*, owner: str) -> CatalogSyncResult`。

- [ ] **Step 1: 写失败测试**（真实 SQLite + FakeSource）
  - `test_three_pages_commit_and_finish_idle`：5 条分 3 页，行数与内容正确、cursor=最大 id、pending=0、status=idle、result.pages=3。
  - `test_second_run_only_fetches_new_ids`：第一次跑完后源只剩新 id，第二次 inserted=1、updated=0。
  - `test_existing_row_is_updated_on_cold_start`：预置 id=1 的旧标题，源返回同 id 新标题，跑完标题更新且行数不变。
  - `test_page_failure_rolls_back_and_marks_failed`：第 2 页抛 `AppError(BAD_CASE_QUERY_TIMEOUT)`，第 2 页数据不在库、cursor 停在第 1 页、status=failed、last_error 稳定码。
  - `test_max_pages_stops_without_failure`：`max_pages=1` 时只写一页，剩余 pending>0、status=idle、exhausted=False。
- [ ] **Step 2: 运行失败**。
- [ ] **Step 3: 实现** 游标循环；`get_state or initialize`；`mark_running`；每页 `fetch_page(after_id=cursor, offset=0, limit=page_size)` → 空页 break → max_id ≤ cursor 抛 `BAD_CASE_QUERY_INVALID_RESPONSE` → `commit_page`；结束时 `mark_idle`；异常 `mark_failed` 后重抛。
- [ ] **Step 4: 运行通过**。
- [ ] **Step 5: 提交** `git commit -m "feat(api): add catalog sync service with cursor paging (#176)"`

### Task 6: 调度、状态聚合与 API 接线

**Files:**
- Create: `apps/api/app/service/acquisition/bad_case_catalog_sync_coordinator.py`
- Modify: `apps/api/app/main.py`
- Modify: `apps/api/app/api/acquisition.py`
- Modify: `apps/api/app/service/bad_cases/service.py`
- Modify: `apps/api/app/service/problems/service.py`
- Test: `apps/api/tests/m6-16-bad-case-catalog-sync/test_catalog_sync_coordinator.py`
- Test: `apps/api/tests/m6-16-bad-case-catalog-sync/test_status_api.py`

**Interfaces:**
- Produces: `CatalogSyncStatus(synced, unsynced, last_bad_case_id, status, last_run_at, last_error)`；`BadCaseCatalogSyncCoordinator(jobs, repository, settings, service, *, clock)` with `available`、`reconcile()`、`trigger(source)`、`run_once()`、`start()`、`stop()`、`status()`。
- Produces: `AcquisitionStatusResponse.bad_case_catalog_sync: BadCaseCatalogSyncSummary`、`bad_case_analysis: BadCaseAnalysisSummary`（camelCase JSON `badCaseCatalogSync` / `badCaseAnalysis`）。
- Produces: `ProblemService.analysis_progress()` 代理 `BadCaseService.analysis_progress()`。

- [ ] **Step 1: 写失败测试**
  - coordinator：未配置时 `status().status == "unavailable"` 且 `trigger` 不提交；已有同 kind 活跃 job 时 `trigger` 返回 skipped；`start()` 会立即触发一次并起定时任务；`reconcile()` 把无活跃 job 的 `running` 复位为 `failed/BAD_CASE_CATALOG_SYNC_INTERRUPTED`。
  - status API：注入 fake catalog source 与混合分析数据，断言 JSON 含 `badCaseCatalogSync` 与 `badCaseAnalysis` 五个计数、camelCase 字段名；`bad_cases` 为空时三个块返回 0 且 200。
- [ ] **Step 2: 运行失败**。
- [ ] **Step 3: 实现** coordinator（单飞、启动立即跑、interval 循环、状态聚合）；`main.py` 构建 client/repo/service/coordinator、注册 handler、lifespan 启停与关闭 client；`acquisition.py` 加 DTO 与 route 组装；`BadCaseService.analysis_progress` 与 `ProblemService` 代理。
- [ ] **Step 4: 运行通过** 同 Step 2；再跑 `pnpm test:db`。
- [ ] **Step 5: 提交** `git commit -m "feat(api): schedule catalog sync and expose status (#176)"`

### Task 7: 契约再生

**Files:**
- Modify: `packages/contracts/openapi.json`（生成）
- Modify: `packages/contracts/src/generated/api.d.ts`（生成）

- [ ] **Step 1: 运行** `pnpm contract:generate`
- [ ] **Step 2: 校验** `pnpm contract:check`，预期无 diff。
- [ ] **Step 3: 提交** `git commit -m "chore(contracts): regenerate status contract (#176)"`

### Task 8: 前端浮层四段

**Files:**
- Modify: `apps/web/src/components/layout/TopNav.vue`
- Modify: `apps/web/src/utils/syncStatus.ts`
- Modify: `apps/web/src/components/layout/TopNav.test.ts`
- Modify: `apps/web/src/test/server.ts`
- Test: 同上测试文件

**Interfaces:**
- Produces: `catalogSyncStatusLabel(status)`、`catalogSyncErrorLabel(code|null)`。
- 浮层 DOM 顺序：`[data-testid="sync-problems"]`? 改为 `sync-catalog` → `sync-problem` → `sync-normalization` → `sync-analysis`；数字文案固定为“总 N · 已同步 N · 未同步 N”“已分析 N · 待分析 N”“问题 N · 非问题 N”。

- [ ] **Step 1: 写失败测试**
  - `renders four sync sections in order`：`textContent` 中“问题数量”<“问题轨迹”<“会话归一化”<“归因分析”。
  - `shows catalog counts and analysis counts`：断言 136/128/8、96/40、58/38。
  - `shows catalog unavailable copy` 与 `shows zero state with 0/0 badge`。
- [ ] **Step 2: 运行失败** `pnpm test:web -- TopNav`（或 `pnpm --filter @harness/web exec vitest run src/components/layout/TopNav.test.ts`）。
- [ ] **Step 3: 实现** 按原型四段重排；catalog 状态映射 unavailable → “未配置坏例查询服务”；analysis 无状态、只显示计数；徽标保持 `问题轨迹 synced/total`。
- [ ] **Step 4: 运行通过**；再跑 `pnpm typecheck:web` 与 `pnpm lint:web`。
- [ ] **Step 5: 提交** `git commit -m "feat(web): show four-section sync popover (#176)"`

### Task 9: 文档、Agent Note 与流程状态

**Files:**
- Modify: `plans/fullstack-design/05-api-design.md`（§4.8 状态响应）
- Modify: `plans/fullstack-design/06-database-design.md`（问题侧边界 + 状态表）
- Modify: `docs/architecture.md` / `docs/architecture.en.md`
- Create: `.agents/notes/implemented/feature/2026-10-30-bad-case-catalog-sync.md`
- Modify: `.agents/flow/issues/m6-bad-case-catalog-sync.md` / `.en.md`（status → in-progress）
- Test: `pnpm lint:docs`、`pnpm verify:docs`、`pnpm verify:flow`

- [ ] **Step 1: 更新文档与 note**（现状口径，不写变更史）
- [ ] **Step 2: 重录 i18n** `pnpm record:i18n -- docs/architecture.md` 与 issue 三件套
- [ ] **Step 3: 运行门禁** `pnpm lint:docs && pnpm verify:docs && pnpm verify:flow`
- [ ] **Step 4: 提交** `git commit -m "docs: document catalog sync and analysis status (#176)"`

### Task 10: 整体验证与差异修复

- [ ] **Step 1: 后端全量** `pnpm test:api`、`pnpm test:db`、`pnpm typecheck:api`、`pnpm lint:api`
- [ ] **Step 2: 前端** `pnpm test:web`、`pnpm typecheck:web`、`pnpm lint:web`
- [ ] **Step 3: 契约/流程/文档** `pnpm contract:check`、`pnpm verify:flow`、`pnpm verify:docs`、`pnpm verify:bundle`
- [ ] **Step 4: 设计差异核对** 逐条对照设计 §3–§9（字段映射、错误码、计数器、四段顺序），差异直接修复并补测试
- [ ] **Step 5: UI 差异核对** 重跑 `capture.mjs`，与原型四段截图逐项比对（顺序、文案、徽标、390px）
- [ ] **Step 6: 提交** 如有修复 `git commit -m "fix: align catalog sync with design (#176)"`

### Task 11: E2E 与冒烟

**Files:**
- Create: `tests/e2e/support/mock_catalog_upstream.py`
- Create: `tests/e2e/m6-16-bad-case-catalog-sync.test.mjs`
- Create: `reports/2026-10-30/m6-16-smoke/collect-smoke.mjs`
- Create: `reports/2026-10-30/m6-16-smoke/smoke-report.html`、`report-data.json`、`screenshots/*.png`

**Interfaces:**
- Mock 服务同时提供：`GET /bad-cases`（分页目录）、`GET /sessions/{id}/children`（接口 1）、`GET /sessions/{id}/trajectory`（接口 2，NDJSON）。
- E2E 用 `HE_BAD_CASE_QUERY_BASE_URL/TOKEN` 与 `HE_SESSION_QUERY_BASE_URL/TOKEN` 指向同一 mock，验证“目录同步 → bad_cases 入库 → 根会话轨迹补齐 → 会话可查”。

- [ ] **Step 1: 写 mock 服务与 E2E 测试**
  - mock 返回 2 页目录（3 条，第二页空）、1 个 root + 1 个 child 的 children/trajectory。
  - 断言：登录后 `/api/acquisition/status` 的 `badCaseCatalogSync.synced` 最终为 3、`unsynced` 为 0；`/api/sessions` 出现对应会话与问题。
- [ ] **Step 2: 运行失败** `pnpm test:e2e -- "m6-16"`
- [ ] **Step 3: 补齐实现缺口**（只改实现，不放宽断言）。
- [ ] **Step 4: 写冒烟采集与报告**：按 `.agents/skills/computer-use-smoke-reporting` 的报告结构，用 CDP 截图，不调用 `.agents/skills/computer-use` 的方法。
- [ ] **Step 5: 运行通过** E2E 与冒烟采集；报告写入 `reports/2026-10-30/m6-16-smoke/`。
- [ ] **Step 6: 提交** `git commit -m "test: add catalog sync e2e and smoke report (#176)"`

## Execution Choice

用户已指定“使用 superpower 完成 issue 开发”，本计划采用 **native** 执行：由本会话按任务 TDD 实现，最后统一做整分支检视、冒烟、PR 与 CI。
