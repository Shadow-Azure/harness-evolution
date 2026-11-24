# 实现 bad case 同步源工厂化：父类 + 工厂 + ClaudeUpstream 子类与写者归属

[English](bugfix-bad-case-sync-source-factory-impl.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-47
milestone: bugfix
depends: []
priority: P2
status: in-progress
scope:
  - .agents/flow/issues/bugfix-bad-case-sync-source-factory-impl*
  - .agents/notes/**
  - .agents/flow/issues/bugfix-bad-case-sync-source-factory-design*
  - .agents/flow/issues/bugfix-claude-edit-tool-surface*
  - .agents/flow/issues/bugfix-deploy-contract-ci*
  - apps/api/app/**
  - apps/api/alembic/**
  - apps/api/tests/**
  - tests/e2e/**
  - scripts/doc-budgets.manifest.json
  - .env.example
  - docs/architecture.md
  - docs/architecture.en.md
  - docs/architecture.i18n.yaml
  - plans/fullstack-design/06-database-design.md
  - plans/fullstack-design/12-bad-case-catalog-sync.md
  - plans/fullstack-design/16-bad-case-sync-source-factory.md
adr:
  - ../../notes/implemented/architecture/2026-11-23-bad-case-sync-source-factory.md
github:
  number: 560
  url: https://github.com/Shadow-Azure/harness-evolution/issues/560
```

## 背景

[第 16 章设计](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md)已定稿（#548 / bugfix-42），但生产代码未变：global 源线仍是 `HttpBadCaseCatalogSource` 与 `HttpSessionQuerySource` 两个平级 HTTP 客户端、`main.py` 两段过程式装配、`BadCaseRootSyncService._sync_root` 内联 if/else 各自一套 BFS；`.env` 没有 global 线显式开关；目录同步对同 id 的已上报行无条件覆盖 13 个上游列并将其计入 `updated`。用户明确要求新增 issue 并要求实现，不接受只交付设计文档。

## 目标

- 新增 `apps/api/app/third_party_api/bad_case_sync_source/` 三件：父类 `BaseBadCaseSyncSource`、子类 `ClaudeUpstreamBadCaseSyncSource`、工厂 `BadCaseSyncSourceFactory`；目录分页与会话获取都走父类模板方法、子类实现。
- global 线开关收敛为 `HE_BAD_CASE_SYNC_PROVIDER`，工厂在装配期读取一次；未设置返回 `None`，未知值启动失败；有旧端点凭据但无 provider 时装配期 warning。
- `_sync_root` 改为「冻结快照 → 统一 fetcher」一张映射、一个循环；global 路径经合成 `SessionSourceEnvelope` 复用既有 `SessionSourceFactory` 投影，删除 `_payload()`，以 parity 测试锁定产出不变。
- `bad_cases` 新增 `origin ∈ {report, catalog}`（含回填迁移）；上报写 `report`，目录同步只更新 `catalog` 行，`report` 行跳过并计入 `skipped`；删除跨方言 upsert。
- 装配缝收敛为 `create_app(bad_case_sync_source=…)`；coordinator 的 `available` 统一由工厂产物是否为 `None` 决定。
- 同步修订 `.env.example`、`docs/architecture.md`、第 12 章 §4.3/§5.1 与 Agent Note 状态。

## 设计依据

- [16 §1 现状盘点](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s1)：两条来源线与装配段的逐文件证据。
- [16 §2 差距分析](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s2)：R1–R7 七项缺口。
- [16 §3 目标设计](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s3)：父类/子类/工厂、开关矩阵、写者归属与跳过计数。
- [16 §5 目录同步数据流](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s5) 与 [16 §6 root 同步数据流](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s6)：逐步 JSON 对照。
- [16 §7 兼容与风险](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md#s7)：快照扩展、行为兼容、测试影响面与实施顺序。
- [Agent Note](../../notes/implemented/architecture/2026-11-23-bad-case-sync-source-factory.md)：三项决策与被否方案。

## 实现内容

- **新模块**：`base.py` 定义 `BaseBadCaseSyncSource`（`fetch_bad_case_page` / `fetch_session` 模板方法，`fetch_page` / `fetch_trajectory` / `list_children` / `build_envelope` / `close` 与 `from_settings` 抽象钩子）；`claude_upstream.py` 封装两个 `httpx.AsyncClient`、Bearer、超时、重试、退避与 `ClaudeUpstreamEnvelopeFactory`，显式声明 `runtime_key="claude-code"`；`factory.py` 提供注册、`provider_key`、未配置返回 `None`、未知 provider 启动失败。
- **目录同步**：服务依赖改为 `BaseBadCaseSyncSource | None` 并调用 `fetch_bad_case_page`；`CatalogSyncResult` / job 结果新增 `skipped`；`BadCaseCatalogSyncRepository.commit_page` 改为查询 `origin` 后三分流，显式 `INSERT` + 仅 `origin="catalog"` 的条件 `UPDATE`，`IntegrityError` 经保存点重试后归入跳过；删除 `_upsert_statement` 与方言分支。
- **root 同步**：`SessionSourceSnapshot` 新增仅 global 可用的可选 `provider`（report 带 provider、global 带模板/运行时一律拒绝）；`_select_source` 把当前源 provider 冻结进 global 快照；`_sync_root` 用 `ReportSessionFetcher` / global 源的 `fetch_session` 统一循环，删除 `_payload()` 与两套 BFS。
- **装配与开关**：`Settings.bad_case_sync_provider` 对应 `HE_BAD_CASE_SYNC_PROVIDER`；`create_app` 在未注入时调用工厂，两个 coordinator 接受 `available`；lifespan 关闭一个同步源与 report fetcher 客户端；旧 `session_query_source=` / `bad_case_catalog_source=` 注入缝删除。
- **数据迁移**：`0032_bad_case_origin` 增加 `origin` 列（默认 `catalog`），按「非默认 workspace 或 `session_source` 非空 → report，否则 catalog」回填；上报写 `origin="report"`，重报不改归属。
- **测试与文档**：改 existing 夹具为新父类假实现；新增工厂/子类/parity/写者归属/回填测试；更新 revision 断言；`.env.example` 增开关说明；第 12 章、`docs/architecture.md` 与 Agent Note 同步。

## 实施步骤

1. 新增 issue 三件套并 `flow:sync` 回填 GitHub 编号，状态转 `in-progress`。
2. 落迁移与写者归属：`origin` 列 + 回填 + 上报写 `report` + 目录三分流 + `skipped` 计数，先锁数据正确性。
3. 落新模块三件与 parity 测试，不接线。
4. 扩 `SessionSourceSnapshot.provider` 与 `_select_source` 冻结，`_sync_root` 收敛为单循环，删 `_payload()`。
5. 切换装配：工厂、`create_app(bad_case_sync_source=…)`、coordinator `available`、lifespan 关闭链与旧注入缝删除。
6. 配置与文档同步，跑聚焦测试、API 静态门禁、流程/文档门禁与契约检查，提交并提 PR。

## 依赖与交付边界

- 依赖：[第 16 章设计](../../../plans/fullstack-design/16-bad-case-sync-source-factory.md)已定稿并合入 `main`（PR #550）。
- 交付边界：只改 bad case 同步源、目录/root 同步、装配、迁移、测试、`.env.example` 与相关文档；不新增 provider 并存、不改 `kind="global"` 数据标签、不为状态接口新增 `skippedBadCases` 契约字段。
- 上报线协议与错误码不变；global 线的 payload 产出一致性由 parity 测试锁定。

## 独立验证

```sh
pnpm test:api -- tests/m6-15-bad-case-session-sync tests/m6-16-bad-case-catalog-sync tests/m9-07-report-session-source tests/bugfix-47-bad-case-sync-source-factory
pnpm lint:api
pnpm typecheck:api
pnpm contract:check
pnpm verify:flow
pnpm lint:docs
pnpm verify:docs
```

- 聚焦 API 测试覆盖：工厂未配置/未知 provider/重复注册、子类关闭两个客户端与 envelope 合成、global 与 report 的 `SessionInfo` parity、provider 冻结与旧快照、已上报行跳过与 `skipped`、`origin` 回填。
- `lint:api`、`typecheck:api`、`contract:check`、`verify:flow`、`lint:docs`、`verify:docs` 全绿。

## 验收标准

- global 线只由 `HE_BAD_CASE_SYNC_PROVIDER` 开启；未设置时工厂返回 `None`，目录与 root 状态均为 `unavailable`；未知值在装配期失败。
- 目录分页与会话获取都先调用父类模板方法；`main.py` 不再手写 HTTP 客户端、鉴权头、重试参数与两段 if 块；新增上游只需一个子类 + 注册。
- `_sync_root` 只有一张 fetcher 映射与一个遍历循环；global 路径经 `SessionSourceFactory.create("claude-code").project` 产出 `SessionInfo`，payload 与旧 `_payload()` 逐字段相同（含 main `agent_meta=None`、subagent `{"parentAgentId": …}`、`runtime_key="claude-code"`）。
- `bad_cases.origin` 首次写入决定归属；目录同步不覆盖 `origin="report"` 的行，跳过数进入 `skipped`，游标与计数同事务推进。
- 旧快照 `{"kind":"global"}` 仍可领取；带 `provider` 的新快照在 report 上被拒；错误码与重试语义不变。
- `.env.example`、`docs/architecture.md`、第 12 章 §4.3/§5.1 与 Agent Note 与实现一致。

## 门禁与 CI

- `pnpm test:api -- tests/m6-15-bad-case-session-sync tests/m6-16-bad-case-catalog-sync tests/m9-07-report-session-source tests/bugfix-47-bad-case-sync-source-factory`
- `pnpm lint:api`、`pnpm typecheck:api`、`pnpm contract:check`
- `pnpm verify:flow`、`pnpm lint:docs`、`pnpm verify:docs`、`pnpm test:gates`
- 提交与 PR 标题带 `(#N)`；PR 描述列出迁移、parity 与写者归属证据。

## 非目标

- 不新增第二个上游实现、不支持多 provider 并存；不改 `bad_case_root_sync.source_kind="global"` 数据标签。
- 不改上报接口协议、workspace 凭据语义与错误码；不为状态接口新增 `skippedBadCases`。
- 不改遍历/租约/重试阶梯与 replay 解析链；不重构无关的 acquisition 模块。
- 不清理历史快照；回滚兼容按第 16 章 §7.1 的启动 re-arm 处理。
