# bad_cases 目录同步字段降级

[English](m6-catalog-field-fallback.en.md) | 中文

```yaml flow
kind: issue
id: m6-17
milestone: m6
depends:
  - m6-16
priority: P1
status: in-progress
scope:
  - apps/api/**
  - tests/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
  - docs/**
adr: []
github:
  number: 179
  url: https://github.com/Shadow-Azure/harness-evolution/issues/179
```

## 背景

目录同步把上游 items 直接映射到 `bad_cases`，但上游的 `object_name` / `object_type` 可能为 null。客户端当前把二者当必填非空字符串，任何一条 null 都会让整页判 `BAD_CASE_QUERY_INVALID_RESPONSE`，阻塞整个目录同步；而 `bad_cases.object_name` / `object_type` 是 NOT NULL，不能直接落 null。

## 目标

- 客户端允许 `object_name`、`object_type` 为 null，其余必填字段仍严格校验。
- 存储映射降级：`object_name` 为空时，`source` 为 `code_reivew` / `code_review` 取 `code-review`，否则取 `source`，`source` 也为空时取固定值 `unknown`；`object_type` 为空时取 `skill`。
- 降级只发生在目录同步的写入映射，不改变 `bad_cases` 表结构、读取路径与已有存量行。
- 补客户端解析与服务映射测试，覆盖 null、空字符串、source 缺失与 `code-review` 别名。

## 设计依据

- [12 §3.2 字段映射](../../../plans/fullstack-design/12-bad-case-catalog-sync.md)：接口字段到表列的映射与 `title` 改名。
- [12 §4.3 已存在记录的更新](../../../plans/fullstack-design/12-bad-case-catalog-sync.md)：upsert 写入的字段范围。
- [06 §4.1 bad_cases](../../../plans/fullstack-design/06-database-design.md)：`object_name` / `object_type` 为 NOT NULL。
- 实现冲突时以 12 章和 06 §4.1 为准。

## 实现内容

- `app/third_party_api/bad_case_query/models.py`：`object_name` / `object_type` 改为可选，保留长度上限；`extra="forbid"` 与其余必填校验不变。
- `app/service/acquisition/bad_case_catalog_sync.py`：`_row` 做降级映射——`object_name` 显式值优先；为空且 `source` 为 `code_reivew` / `code_review` 时取 `code-review`；否则取 `source`；`source` 也为空取 `unknown`。`object_type` 为空取 `skill`；`CatalogCaseRow` 仍保持非空类型。
- 测试：客户端允许 null；服务覆盖 source 兜底、`code-review` 别名、`unknown` 兜底，以及显式 `object_name` 不被覆盖。
- 文档：12 §3.2 补一行降级规则；Agent Note 决策段补一句最终兜底值。

## 实施步骤

1. 写失败测试：客户端解析 null、服务映射 source/skill/unknown。
2. 放宽模型并实现 `_row` 降级，运行目标测试。
3. 更新设计与 Agent Note，跑文档门禁。
4. 全量相关测试、类型检查与 lint。

## 依赖与交付边界

- 依赖：m6-16（目录同步主体）。
- 非目标：不回填存量行、不改变 `title` / `bad_case_session_id` 的校验、不改变问题读接口、不修改表结构。

## 独立验证

```sh
pnpm test:api -- tests/m6-16-bad-case-catalog-sync
pnpm test:db
pnpm typecheck:api
pnpm lint:api
pnpm verify:flow
pnpm lint:docs
```

- null `object_name` + source 有值时，落库 `object_name` 等于 source。
- source 为 `code_reivew` / `code_review` 且 `object_name` 为 null 时，落库 `code-review`。
- null `object_type` 落库为 `skill`。
- source 也缺失时落库 `unknown`，不发生 500 或整页拒绝。
- 其余必填字段缺失仍判 `BAD_CASE_QUERY_INVALID_RESPONSE`。

## 验收标准

- 上游返回 null `object_name` / `object_type` 时目录同步继续成功，不再整页失败。
- 降级规则与顺序为 `object_name` 显式值 → `code-review` 别名（source 为 `code_reivew` / `code_review`）→ `source` → `unknown`；`object_type → skill`。
- 非空值保持原样，不被降级覆盖。
- 相关测试与门禁全绿。

## 门禁与 CI

- `pnpm test:api` / `pnpm test:db` / `pnpm typecheck:api` / `pnpm lint:api`
- `pnpm verify:flow` / `pnpm lint:docs` / `pnpm verify:docs`
- `pnpm contract:check`（客户端模型不进入 inbound OpenAPI，预期无变化）

## 非目标

- 不回填或重写 `bad_cases` 存量行。
- 不为 `bad_case_type` / `bad_case_session_id` / `title` / 时间戳增加降级。
- 不改前端展示与浮层统计。
