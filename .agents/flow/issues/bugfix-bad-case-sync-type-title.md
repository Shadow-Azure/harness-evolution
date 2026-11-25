# 上游同步 bad case 的类型为空与标题超长处理

[English](bugfix-bad-case-sync-type-title.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-56
milestone: bugfix
depends:
  - m6-16
  - m6-17
priority: P2
status: done
scope:
  - .agents/flow/issues/bugfix-bad-case-sync-type-title*
  - .agents/flow/issues/bugfix-edit-insert-anchor-multiline*
  - .agents/notes/**
  - apps/api/app/service/acquisition/bad_case_catalog_sync.py
  - apps/api/app/third_party_api/bad_case_query/models.py
  - apps/api/tests/m6-16-bad-case-catalog-sync/**
  - plans/fullstack-design/12-bad-case-catalog-sync.md
  - plans/2026-11-25-pr606-review.md
adr: []
github:
  number: 600
  url: https://github.com/Shadow-Azure/harness-evolution/issues/600
```

## 背景

### 问题描述

目录同步 `bad_case_catalog_sync` 按页读取上游 `bad_cases`，整页经 `BadCasePage` 严格校验后写入本地表。上游数据里已经出现 `bad_case_type` 为 null 和 `title` 超长的条目：前者违反 `BadCaseItem.bad_case_type` 的必填字符串约束；后者在同步链路里没有 200 字符截断（传输模型与 `bad_cases.title` 列宽都是 255）。只要页内有一条这样的 item，整页 `model_validate` 就会失败，`HttpBadCaseCatalogSource` 把它映射为 `BAD_CASE_QUERY_INVALID_RESPONSE`（502），`BadCaseCatalogSyncService.run` 回滚该页、保持游标并 `mark_failed`；下一轮定时任务从同一游标重试同一页，单条脏数据因此成为 poison pill，后续所有 bad case 都同步不进来。

- 现象一：`bad_case_type` 为 null 时整页解析失败，按需求应落库 `self`。
- 现象二：`title` 超过 200 字符时按需求应截断到 200；当前 201–255 字符能落库但不截断，超过 255 才整页失败。
- 影响：游标停在坏页之前，已同步数量不再增长，同步浮层只显示稳定的 `BAD_CASE_QUERY_INVALID_RESPONSE`，无法定位到具体 case 或字段。

### 分析过程

按调用链、数据契约、实测与失败语义四步核对，证据如下。

1. 调用链：`BadCaseCatalogSyncService.run` 调 `BaseBadCaseSyncSource.fetch_bad_case_page`，再到 `HttpBadCaseCatalogSource.fetch_page` → `_parse` → `BadCasePage.model_validate`；任何 `ValidationError` 都在 `http.py` 的 `_parse` 被收敛为 `BAD_CASE_QUERY_INVALID_RESPONSE`。
2. 数据契约：`models.py:18` 要求 `bad_case_type` 非空（`min_length=1`），`models.py:24` 把 `title` 上限定为 255；`domain.py:306` 的 `bad_case_type` 是 `VARCHAR(16) NOT NULL`，`domain.py:312` 的 `title` 是 `VARCHAR(255) NOT NULL`；迁移 `0010_bad_case_title.py` 只建 255 列，代码库里没有 200 约束。
3. 实测模型：用 `apps/api/.venv/bin/python` 直接构造 `BadCasePage`（临时脚本，不入库），再让同一 payload 走 `HttpBadCaseCatalogSource._parse`。
4. 失败语义：`bad_case_catalog_sync.py` 的 `run` 只有在 `commit_page` 成功后才更新游标；异常分支只 `mark_failed` 后重抛。`test_catalog_sync_service.py` 的 `test_page_failure_rolls_back_and_marks_failed` 断言失败页不写行、游标停在上一页，说明同一坏页会被反复重试。
5. 对照历史：m6-17（#179）已为 `object_name` / `object_type` 做 null 降级，并在非目标里明确排除 `bad_case_type` / `title`；读路径的总览聚合只统计 `bad_case_type IN ('self', 'discovery')`（`crud/overview.py:119`），把 null 归一成 `self` 能让这些 case 正常进入统计，而不是被静默排除。

实测输出如下，后两行是同一 payload 经 `_parse` 的结果。

```text
bad_case_type=null     -> ValidationError type=string_type loc=('items', 0, 'bad_case_type')
title=201              -> page OK, item.title len=201
title=255              -> page OK, item.title len=255
title=256              -> ValidationError type=string_too_long loc=('items', 0, 'bad_case_title')
title=300              -> ValidationError type=string_too_long loc=('items', 0, 'bad_case_title')
bad_case_type=null     -> AppError code=BAD_CASE_QUERY_INVALID_RESPONSE
title=256              -> AppError code=BAD_CASE_QUERY_INVALID_RESPONSE
```

因此问题不是上游数据不可修复，而是同步层缺少针对这两个字段的归一化；且当前 200 口径在代码里完全不存在，实测阈值是 255。

### 根因

根因是传输契约与写入映射之间没有归一化层，而页级校验又是全有或全无。

- 契约错位：`BadCaseItem` 把上游数据当成已经满足本地 NOT NULL 与长度约束的成品，`bad_case_type` 非空、`title` 上限 255；上游实际允许 null 和更长文本。
- 缺少归一化：`_row` 直接赋值 `item.bad_case_type` 与 `item.title`，没有默认值或截断，所以上游的这两种形状只能以整页失败告终。
- 失败放大：`BadCasePage.model_validate` 是页级原子校验，服务端只有在整页 `commit_page` 成功后才推进游标；单条坏行阻塞整页，且下一轮从同一游标重试，影响面从一行扩大到全部后续数据。
- 历史缺口：m6-17 的降级只覆盖 `object_name` / `object_type`，`bad_case_type` / `title` 被明确列为非目标。

### 结论

- 两条规则都属于同步写入策略：`bad_case_type` 为 null（含缺失）落 `self`；`title` 超过 200 字符截断到 200。
- 传输模型必须接受上游的真实形状（可空类型、超长标题），否则归一化逻辑没有机会执行；`BadCasePage` 的排序、唯一、limit/total 与回显校验保持不变。
- 归一化只放在 `_row` 的写入映射，不改表结构、读路径、上报接口与存量行。
- 当前 255 的实际上限与需求的 200 口径不一致，应按 200 收紧；200 也是归因侧短标题预算（`attribution.py:436` 与 `attribution_executor.py:118` 都取 `[:200]`）。

## 目标

- 上游 `bad_case_type` 为 null 或缺失时，同步成功并落库 `self`。
- 上游 `title` 超过 200 字符时，同步成功并只落库前 200 个字符；不超过 200 时原样保留。
- 放宽仅限这两个字段的传输校验；`BadCasePage` 的结构校验、其他必填字段与页级回滚语义不变。
- 补客户端与服务测试，并在设计文档与 Agent Note 记录归一化规则和取舍。

### 最推荐的解决方案

推荐在 `BadCaseItem` 与 `_row` 两处做最小改动，保持 m6-17 的“传输放宽、写入归一”分层；不改表、不改读路径、不改页级事务。

1. `BadCaseItem`：`bad_case_type` 改为 `str | None`（保留 1–16 长度约束），`title` 去掉 255 上限（保留 `min_length=1`）；`extra="forbid"`、时间戳时区校验与 `BadCasePage` 的所有结构校验保持原样。
2. `_row`：`bad_case_type=item.bad_case_type or "self"`，`title=item.title[:200]`；其他字段的映射与空值降级不变。
3. 测试：客户端解析 null type 与 201/300 字符 title；服务断言 null type 落 `self`、200 字符原样、201/300 截到前 200、显式 `discovery` 不被覆盖；补一条“其他非法字段仍整页拒绝”的回归。
4. 可观测性：归一化发生时在 `_row` 记录一次结构化 info 日志（`badCaseId` 与命中的字段），不新增状态列，用于区分上游漂移和本地逻辑错误。
5. 文档：在 12 §3.2/§3.3 写明两条归一化规则，并新增 Agent Note 记录为什么放在写入映射、标题截断为什么是有损的、为什么列宽仍是 255。

## 设计依据

- [12 §3.2 字段映射](../../../plans/fullstack-design/12-bad-case-catalog-sync.md)：字段映射、`title` 改名与可选字段处理。
- [12 §3.3 校验、错误与串行](../../../plans/fullstack-design/12-bad-case-catalog-sync.md)：严格模型与 `BAD_CASE_QUERY_INVALID_RESPONSE` 的边界。
- [12 §4.3 已存在记录的更新](../../../plans/fullstack-design/12-bad-case-catalog-sync.md)：upsert 写入的字段范围。
- [06 §4.1 bad_cases](../../../plans/fullstack-design/06-database-design.md)：`bad_case_type` / `title` 的 NOT NULL 与列宽。
- 实现冲突时以第 12 章与 06 §4.1 为准。

## 实现内容

- `models.py`：放宽 `bad_case_type` 与 `title` 的传输校验，保留其余字段约束。
- `bad_case_catalog_sync.py`：在 `_row` 归一化 type 与 title，并记录归一化日志。
- `test_bad_case_query_client.py` / `test_catalog_sync_service.py`：覆盖 null、200、201、300、显式值保留与其他非法字段拒绝。
- `plans/fullstack-design/12-bad-case-catalog-sync.md` 与 Agent Note：记录规则与取舍。

## 实施步骤

1. 先写失败测试：客户端接受 null type 与 300 字符 title；服务断言 `self` 与前 200 截断。
2. 放宽 `BadCaseItem`，在 `_row` 实现归一化，运行聚焦测试。
3. 补日志断言与“其他非法字段仍拒绝”的回归。
4. 更新 12 章与 Agent Note，跑文档门禁与流程门禁。

## 依赖与交付边界

- 依赖：m6-16（目录同步主体）、m6-17（已有字段降级）。
- 非目标：不改表结构或新增迁移、不回填存量行、不改页级原子性与游标语义、不跳过坏行、不为其他字段增加降级、不改前端。

## 独立验证

```sh
pnpm test:api -- tests/m6-16-bad-case-catalog-sync
pnpm test:db
pnpm typecheck:api
pnpm lint:api
pnpm verify:flow
pnpm lint:docs
```

- null type 的页能通过解析，落库 `bad_case_type='self'`。
- `title` 为 200 字符时原样落库；201 与 300 字符时落库为前 200 字符。
- 显式 `self` / `discovery` 与短标题不被覆盖。
- 其他非法字段仍让整页判 `BAD_CASE_QUERY_INVALID_RESPONSE`，失败页不推进游标。
- 归一化日志包含 `badCaseId` 与字段名。

## 验收标准

- 上游返回 null/缺失 `bad_case_type` 时同步成功，落库 `self`。
- 上游返回超过 200 字符的 `title` 时同步成功，落库前 200 字符。
- 200 字符以内与非空 type 的值保持原样。
- 相关测试、类型检查、lint 与流程/文档门禁全绿。

## 门禁与 CI

- `pnpm test:api` / `pnpm test:db` / `pnpm typecheck:api` / `pnpm lint:api`
- `pnpm verify:flow` / `pnpm lint:docs` / `pnpm verify:docs`
- `pnpm contract:check`（客户端模型不进入 inbound OpenAPI，预期无变化）

## 非目标

- 不修改 `bad_cases` 表结构、列宽或新增迁移。
- 不回填或重写存量 `bad_cases` 行。
- 不改变页级事务、游标推进与“坏页整页拒绝”的既有语义。
- 不为 `bad_case_session_id`、`title` 为 null、时间戳等其他字段增加降级。
- 不改前端展示与同步浮层统计。
