# 兼容与退役

[English](compatibility.en.md) | 中文

记录兼容窗口内的 V1 面、触发版本与机械删除条件；理由见 [Agent Note](../.agents/notes/implemented/architecture/2026-11-17-v2-compatibility-retirement.md)。窗口内不删除端点、路由或字段。

## 兼容面

| 面 | 当前行为 | 删除条件 |
|---|---|---|
| V1 读端点 | `GET /api/sessions*`、`GET /api/bad-cases*`、`GET /api/probes/{id}`、`GET /api/catalogs/*`、`POST /api/evolution/probes/query` 与无前缀 `/api/evolution/*` 按用户全部可见空间过滤；`/analysis` 与 `/sessions/{sid}/probes` 只返回 legacy 形状 | V3 启动，且 V2 页面、fixtures、E2E 与文档均无调用 |
| 无空间路由 | `/`、`/sessions/**`、`/errors`、`/evolution/**` 重定向到最近可见空间；多空间歧义进选择页 | V3 启动，且书签、外部链接与 E2E 不再产生无 `wid` 路径 |
| V1 run schema | `attribution_engine='legacy-probe-import'` 的六步游标只读映射为七步 DTO；新 run 只写七步 | 无 legacy run 需读取，且六步类型从契约与页面移除 |
| 可空兼容列 | `bad_case_analysis.probe_id` 与 `probe_reports.cache_key` 可空，容纳 V1 无 probe 的行 | 存量行回填完成，迁移可安全收紧 NOT NULL |
| 内联归因 | `BadCase.analysis` 仍随 `BadCase` 返回并被列表卡读取；V2 错误详情用归因分页/详情 | 列表卡不再读取该字段，且契约消费方已移除 |
| 兼容深链 | 错误详情接受 `?obj=<name>`（原型兼容）；`?issue=`、`?report=` 从未提供兼容 | 已知旧链接过期，`obj` 分支、契约与测试一并删除 |
| legacy 目录同步 | `HE_BAD_CASE_CATALOG_SYNC_ENABLED=false` 默认关闭；启用时只按主键 upsert 默认空间，不进入 V2 主路径 | V3 启动且默认空间不再需要历史导入 |

## 触发版本

下个大版本是 V3，即 V2 之后的第一个主版本；兼容窗口至少覆盖一个已发布 V2 版本。V3 启动前不删除兼容面，也不让新功能依赖兼容行为。

## 机械检查清单

1. 搜索确认无残留：`rg -n "api/sessions|api/bad-cases|api/probes|probes/query|legacy-probe-import|\\bobj=" apps packages tests fixtures docs`。
2. 前端：删除 legacy API helper、`/analysis`、`/probes` 读取与旧路由重定向；更新测试，保留 V2 只调用 `/workspaces/:wid` 的回归断言。
3. 后端与契约：删除 V1 端点、六步适配分支与 legacy 类型；运行 `pnpm contract:generate && pnpm contract:check`。
4. 数据库：先回填 `probe_id`/`cache_key`，再用迁移收紧 NOT NULL；运行 `pnpm test:db && pnpm test:db:mysql`。
5. 数据：确认无新增 legacy run；存量 run 快照或归档后删除读取适配。
6. 测试与 fixtures：删除 legacy 用例，新增“旧路径返回 404/未注册”断言；运行 `pnpm test:api && pnpm test:e2e`。
7. 文档：更新本页、architecture 与 owning Note；运行 `pnpm verify:docs && pnpm verify:flow`。
8. 发布：确认书签、外部上报与客户端文档不再使用无 `wid` 路径，再删除重定向。

## 验证

- 上述命令全绿，`rg` 只命中本页与历史 Note/plans。
- V2 页面、fixtures、E2E 只调用工作空间前缀端点。
- 删除 PR 包含“旧路径不可达”的测试与回滚说明；未满足时保持兼容。
