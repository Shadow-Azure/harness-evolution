# Agent Note: V2 空间基座的单版本迁移

Status: implemented

[English](2026-11-15-v2-workspace-foundation-migration.en.md) | 中文

## Problem

V2 的权限、额度与归因都要求一个空间归属，但 V1 的 `bad_cases`、`evolution_targets`、`evolution_runs` 与 `evolution_run_events` 没有空间列，用户也只有全局角色。迁移必须同时满足三件事：存量行不能变成不可见；V1 写入在空间 API 落地前不能因新列而失败；SQLite 测试库与 MySQL 生产库都要得到同一语义。

SQLite 的 `ALTER TABLE` 能力有限。把父表整表重建来追加外键或改唯一键，会在 `PRAGMA foreign_keys=ON` 下触发 `ON DELETE CASCADE` / `SET NULL`，静默改写子表数据——这正是本迁移要避免的损失。

## Decision

- 单一 Alembic 版本 `0014` 建 `workspaces`、`workspace_members`、`workspace_ingest_credentials`，给 `users` 加 `auth_provider` / `external_subject` 与唯一索引，并给四张业务表加 `workspace_id`、索引和回填。
- 默认空间固定为 `ws-default`；`quota = COUNT(bad_cases) + 50`，名称「默认空间」。用户全部以 `viewer` 写入成员表，全局管理员仍按 `users.role` 直通，不依赖成员行。
- `workspace_id` 带 `DEFAULT 'ws-default'`：空间 API 尚未落地，V1 目录同步、fixture 与内部写入继续落默认空间；显式空间写入由 m7-03 起的调用方负责。该默认值是过渡约定，不是空间隔离的替代。
- MySQL 为 `bad_cases`、`evolution_targets`、`evolution_runs` 追加 `workspace_id` 外键；`evolution_run_events.workspace_id` 按设计只是空间审计冗余列，不加外键。SQLite 不重建父表，因此不追加这些外键，`NOT NULL`、默认值与索引仍然生效。约束语义由应用层在空间服务中补足。
- `evolution_targets` 唯一键从 `(object_type, object_name)` 改为 `(workspace_id, object_type, object_name)`。SQLite 的唯一键变更只重建这一张表，并在重建前后备份、恢复 `evolution_runs.target_config_id`，避免 `SET NULL` 改写 run 快照。
- 空库升级、重复升级、存量回填与跨空间唯一键由 `test:db` 覆盖；MySQL 空库升级在 CI 的 `test:db:mysql` lane 校验。

## Alternatives considered

- **所有方言都整表重建父表来加外键**：SQLite 会级联改写或删除子表行，迁移不可逆地破坏 run、analysis 数据；拒绝。
- **先让 `workspace_id` 可空，等空间 API 再收紧**：存量行会长期不可见，且额度统计与去重查询要到处兜底 NULL；拒绝。
- **在 ORM 模型里声明 workspace 外键**：外部表 `bad_cases` 由 fixture 路径用模型 `create_all` 引导，跨 MetaData 外键无法解析；外键只放在迁移里，模型只表达列与索引。
- **把归因表一起迁入 0014**：多归因、缓存键与 `probe_reports` 语义属于后续归因 issue；单版本里混入会让回滚边界与验收不可分。
- **迁移时按环境变量读取默认空间 ID**：迁移期间应用配置尚未成为 schema 事实源，先固定 `ws-default`，由后续配置接线统一。

## Consequences

- m7-03 起的写路径必须显式传入空间；在它们完成前，遗漏会静默进入默认空间，这是已知的过渡风险。
- SQLite 的空间外键缺失只影响测试/本地库；MySQL 生产库有外键。需要在空间服务里保持同样的不可见空间 404 规则。
- 归因迁移（`probe_reports.workspace_id` 等）留给下一个版本；本版本不承诺多归因查询可用。
- 默认空间名称与 `mark` 是迁移生成值，管理界面可按普通空间展示和改名。
