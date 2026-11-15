# Agent Note: 空间角色依赖与 auth/session 聚合

Status: implemented

[English](2026-11-15-workspace-auth-session.en.md) | 中文

## Problem

登录身份只回答“你是谁”，不回答“你能操作哪个空间”。V1 只有 `users.role` 的全局角色；m7-02 建好了 `workspaces`、`workspace_members` 与业务表的 `workspace_id`，但还没有任何读取路径。若每个业务端点各自查成员表，404/403 语义、角色顺序与批量查询会各写一套；若把空间角色塞进 JWT，成员变更要等 token 过期才生效，撤销也无从谈起。

前端启动还需要一次拿到当前用户与全部可见空间；分成 `me` + 空间列表两个请求会多一次往返，并让“用户与可用空间必须来自同一会话”的约束散落在前端。

## Decision

- `WorkspaceRepository` 独占空间读取：单空间、成员行、按 `created_at DESC, id` 的可见空间列表，以及按空间分组的 `used`、成员数与空间管理员数。列表先取 201 条用于判定截断，聚合只针对入选的空间，查询条数不随空间数增长。
- `require_workspace_role(minimum)` 是统一依赖，从路径参数 `{wid}` 取空间：全局管理员只需空间存在，直接以 `global_admin` 放行；其余用户每请求读 `workspace_members`，按 `viewer < member < space_admin` 比较。空间不存在与不可见共用 `404 WORKSPACE_NOT_FOUND`，角色不足返回 `403 WORKSPACE_FORBIDDEN`。空间角色不写入 token。
- `GET /api/auth/session` 一次返回 `user + workspaces + truncated`：全局管理员看到全部空间且有效角色为 `global_admin`，普通用户只看到成员行对应的空间；每项带实时 `used`、`memberCount`、`spaceAdminCount`。超过 200 个可见空间时只返回前 200 条并置 `truncated=true`。
- `auth/session` 与改密、登出、`me` 同属强制改密期间允许的端点；前端可在改密前先恢复用户与空间。
- 本轮契约直接由 FastAPI OpenAPI 生成 `SessionPayload` 与 `SessionWorkspace`；其余空间管理类型在对应端点落地前保持显式声明。

## Alternatives considered

- **把空间角色写进 access token**：成员变更与撤销要等 token 过期，违反“每请求现查、立即生效”；拒绝。
- **`me` 与空间列表分两个端点**：多一次启动往返，且无法保证两份数据来自同一时刻的会话；拒绝。
- **按空间逐个查 `used` 与成员数**：200 个空间就是 400 次查询；拒绝。
- **不可见空间返回 403**：会暴露空间是否存在，便于枚举；统一 404 拒绝。
- **先取全部空间再在 Python 里截断**：空间数量无上界时会先付出全量聚合成本；在列表查询上限制再聚合。

## Consequences

- m7-05 的成员写操作与 m7-06 起的业务端点复用同一依赖；改成员后无需重新登录即可生效。
- 全局管理员直通仍需先确认空间存在，否则拼写错误的 `wid` 会被当成合法空间。
- `used` 只是实时计数；额度拦截要等上报路径（§4.17）接入。
- 200 条截断是契约的一部分，前端空间切换器必须处理 `truncated=true` 的降级。
- 测试库的 `bad_cases` 仍由 fixture 引导创建，空间测试必须先建外部表。
