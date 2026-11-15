# Agent Note: 空间 bad case 上报的凭据边界、事务额度与幂等

Status: implemented

[English](2026-11-16-workspace-bad-case-ingest.en.md) | 中文

## Problem

m7 已经交付空间、成员与一次性上报凭据，但 `bad_cases` 仍只有 legacy 目录任务一条写入路径：它按游标把上游数据 upsert 到默认空间，既没有额度约束，也不认调用方身份。空间的机器上报需要一个稳定入口，并且三件事必须在并发下也成立：额度不超卖、同一 `badCaseId` 重报不重复占额度、ID 不能被别的空间抢走或覆盖。凭据本身还必须只够做这一件事——泄漏一个 `whk_` 令牌不能让调用方读会话、改成员或写别的空间。

## Decision

- 新增 `POST /api/workspaces/{wid}/bad-cases`，鉴权用空间凭据（`Authorization: Bearer whk_…`）。`AuthMiddleware` 只对该 `POST` 路由跳过 access-token 解码，匹配用锚定正则 `^/api/workspaces/[^/]+/bad-cases$`：尾斜杠、子路径与其它方法继续走 JWT，泄漏的凭据在别处一律 401 `AUTH_REQUIRED`。
- 凭据解析放在路由依赖里并复用 `WorkspaceService.verify_credential`：缺失、未知或已撤销 → 401 `CREDENTIAL_INVALID`；凭据空间与 URL 不一致 → 403 `WORKSPACE_FORBIDDEN`；URL 指向不存在的空间 → 404 `WORKSPACE_NOT_FOUND`。凭据先验证，未认证调用方无法枚举空间 id。
- 请求体是封闭的 camelCase 契约（`extra="forbid"`，只认别名），`workspaceId`、snake_case 与未知字段都 422；空间身份只来自 URL 与凭据，body 不参与。
- 一次事务覆盖额度判定与写入：先锁空间行（MySQL `SELECT … FOR UPDATE`；SQLite 没有行锁，用一次 `UPDATE … SET updated_at = updated_at` 取得数据库写锁），再按主键读既有 case，最后插入或更新。`used` 永远是 `COUNT(bad_cases WHERE workspace_id)`，不落列、不缓存；响应头 `X-HE-Workspace-Used` 与 body `workspaceUsed` 取自写后同事务的计数。
- 归属与额度的顺序固定：既有 case 属于其它空间 → 409 `BAD_CASE_ID_CONFLICT`（不搬移、不覆盖、不占额度）；属于本空间 → 200 更新全部上游字段；只有新 ID 才做额度判定，`used >= quota` → 409 `QUOTA_EXCEEDED`（`details: {quota, used}`），旧数据不动。
- 同 ID 并发插入撞主键时捕获 `IntegrityError` 后重读：同空间退化为更新（201 变 200），异空间升级为冲突。锁顺序固定为空间 → case，竞态双方都不会持有对方需要的锁。
- 写入成功后在同一事务里 insert-if-absent 一条 `bad_case_root_sync` 的 `pending` 行，让新根会话立即成为 `bad_case_root_sync` 候选；已 `synced`（吸收态）或 `failed`（退避中）的行保持原状，不会被重报重置。无状态行按 pending 处理的语义不变。
- `last_used_at` 只是排障信息：60 秒节流写入，失败只记日志，绝不把已提交的上报变成 500。
- `BadCaseIngest` / `BadCaseIngestResponse` 进入 FastAPI OpenAPI，`packages/contracts` 由 `pnpm contract:generate` 生成；`QUOTA_EXCEEDED` 与 `BAD_CASE_ID_CONFLICT` 进入共享错误码枚举。

## Alternatives considered

- **body 接受 `workspaceId`**：拒绝。空间身份会有两个来源，凭据与 body 冲突时无法判断谁权威，还会把泄漏凭据变成跨空间写入口。
- **物化 `used` 列**：拒绝。bad case 由上报路径随时插入，没有失效通知的计数器必然陈旧；额度是低频写路径，一次 `COUNT(*)` 走 `(workspace_id, …)` 索引可接受。
- **进程内 `asyncio.Lock` 串行化写入**：拒绝。只在单进程有效，还会掩盖 MySQL 上真正的行锁语义；SQLite 改为在数据库层取得写锁，方言分支显式且只影响本地与测试。
- **`INSERT … SELECT … WHERE (SELECT COUNT(*)) < quota` 单语句**：拒绝。两个方言对同表子查询的可写性不一致，也放弃把冲突与额度映射成不同错误码的能力。
- **root-sync 标记用独立事务**：拒绝。已提交的 case 可能缺候选标记；同一事务里的 insert-if-absent 更简单，失败即整体回滚。
- **把 root-sync 行 upsert 成 `pending`**：拒绝。`synced` 是吸收态、`failed` 有退避，重报重置会重拉已完成的根会话或缩短退避。
- **允许凭据访问所有 `/api/workspaces/**`**：拒绝。凭据不映射用户主体，爆炸半径必须限于「往该空间写 bad case」。
- **容忍 snake_case body**：拒绝。打开 `populate_by_name` 后 `workspace_id` 之类的服务端列名可以被猜着提交，封闭别名更安全。

## Consequences

- SQLite 上每次上报会短暂持有数据库写锁，写路径在这一段全局串行；这是单写者方言的固有代价，本地与测试可接受，生产 MySQL 用空间行锁并发。
- 额度判定新增一次 `COUNT(*)`；`used` 不物化，空间列表与 `auth/session` 继续用同一口径，不存在两套计数。
- 403 与 404 的区分让持有任一有效凭据的调用方知道某个空间 id 是否存在；未认证调用仍统一 401。
- 凭据只证明空间范围，没有 per-agent 身份与速率限制；吊销即时生效的代价是每次上报一次凭据索引查询。
- 根会话状态表新增显式 `pending` 行；调度器「无行即 pending」的分支保留，两者都算候选。
- legacy 目录任务继续只向默认空间插入，冲突时更新上游字段而不改 `workspace_id`；上报路径保证不跨空间覆盖，但不接管目录任务的写入边界。
- MySQL 并发额度测试只在 `HE_DB_URL` 指向 MySQL 的 lane 运行；本地 SQLite 只验证等价语义与串行化分支。
