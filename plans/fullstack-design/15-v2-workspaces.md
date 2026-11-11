# 15 · V2 多用户鉴权接入与工作空间

> 本文回答：多用户身份如何接入（不开放注册）、工作空间/成员/额度/上报凭据的数据模型与接口、既有表如何加上空间维度、权限如何在服务端收口。
> 前置：[README 决策表](README.md) · [01 总体架构](01-architecture.md) · [05 接口设计](05-api-design.md) · [06 数据库设计](06-database-design.md)；配套：[16 总览](16-v2-overview.md) · [17 归因](17-v2-attribution.md)。
> 做 V2 工作空间相关 issue 前先读本文。验收基准：[V2 原型](../ui-prototype-v2/harness-evolution.html)（登录页、空间切换器、空间管理四 Tab、上报接入）与 [design-v2.md](../ui-prototype-v2/design-v2.md)。

## 1. 背景与目标

V1 是单组织共享（决策 D10）：`users` 表 + `admin/member` 两角色，登录即可见全部数据，核心表只记 `created_by`。V2 在此之上引入：

1. **多用户登录，不开放注册**：账号仍由全局管理员创建（或 env 播种唯一管理员）；对外不提供 `POST /api/auth/register`。
2. **预留鉴权接入接口**：把「身份提供方」收敛为一个接缝，后续以极少改动接入 Cookie 会话与 SSO/OIDC（用户信息存储 + 回调匹配），即可完成多用户接入。
3. **多工作空间**：全局管理员（唯一）创建空间、设初始空间管理员、调额度；空间管理员拥有该空间一切操作权限；一个空间多个空间管理员；管理员可把自己加为某空间的空间管理员；空间管理员可添加成员并授予管理员以下的角色。
4. **每空间 bad case 上报接口与额度**：`POST /api/workspaces/{wid}/bad-cases`，POST body 即 `bad_cases` 表类型；上报数量上限（额度）在创建空间时可设、创建后可调。

### 1.1 与原型的三处修正

原型是交互验收基准，落地时按以下决策修正（均已与目标态对齐）：

| 原型行为 | V2 落地决策 | 理由 |
|---|---|---|
| 登录页是「演示账号列表 + 一键进入」 | 生产登录页保持 V1 的 username/password 表单；原型列表仅用于演示 | 不开放注册与账号枚举安全要求 |
| 权限矩阵含「删除工作空间」 | V2 不做空间删除/归档（见 §9 非目标）；原型也无删除入口 | 额度与成员可调已覆盖管理诉求，删除涉及数据归属清算 |
| 「把自己设为空间管理员」按钮对所有人可见 | 仅全局管理员可用（`POST /workspaces/{wid}/members/self-admin`）；普通用户不能自我提权 | 权限矩阵约定「任命/撤销空间管理员」仅全局管理员 |

原型中「Session 精确查询实为 ID 子串匹配」「下钻是行内 ID 链接而非整行点击」两处为有意设计（[16 §5](16-v2-overview.md)），不算偏差。

## 2. 身份与鉴权接入

### 2.1 不变的部分（现有实现直接复用）

现有 identity 栈（[07 §8](07-backend-implementation.md)）全部保留：

- `users` 表：argon2id 哈希、`must_change_password`、`is_active`；`role` 只有 `admin`（全局，唯一账号）/ `member` 两值。
- access token（30min，前端内存）+ refresh token（httpOnly + SameSite=Strict cookie，14d）+ 一次性 SSE 票据。
- 首次登录强制改密（`403 PASSWORD_CHANGE_REQUIRED` 闸门）。
- `GET/POST /api/users` 管理员建号（D18）。

**唯一全局管理员**由播种与建号规则共同保证：env 只播种一个 `admin`；`POST /api/users` 禁止创建 `role=admin`（422 `ROLE_INVALID`），全局管理员账号不可降级。这比在 DB 上加单行约束简单且可解释。

### 2.2 新增：会话聚合接口 `GET /api/auth/session`

前端启动（含刷新恢复登录态）时调用一次，取回「用户 + 可用空间」：

```json
{
  "user": { "id": "u-admin", "username": "admin", "displayName": "林澈", "role": "admin", "mustChangePassword": false },
  "workspaces": [
    { "id": "ws-harness", "name": "Harness 核心研发", "mark": "核心轨迹诊断", "role": "space_admin",
      "quota": 500, "used": 128, "memberCount": 4 },
    { "id": "ws-research", "name": "调研空间", "mark": "", "role": "viewer",
      "quota": 100, "used": 12, "memberCount": 2 }
  ]
}
```

- 鉴权同现有 Bearer（refresh 流程不变）；它等价于 `GET /auth/me` + 「我的空间列表」的登录后必用聚合，属于 [05 §1.1](05-api-design.md) 允许的静态元数据聚合。
- `workspaces[].role` 是该用户在此空间的 `workspace_members.role`；全局管理员在所有空间视为 `space_admin`（未入成员表也返回，`role="space_admin"`、`memberCount` 照实）。
- 前端只依赖本接口的 `user + workspaces` 结构（对应原型 `v2Boot` 的替换点）；空间业务页不再各自拉用户/空间信息。

### 2.3 鉴权接入接缝（预留，V2 不切换默认）

把「认证如何发生」收敛为 identity 服务内部的一个接口 + 一条会话桥，业务与前端契约不变：

```text
service/identity/
  providers.py        # AuthProvider 协议：authenticate(credentials) -> UserRecord | None
  password.py         # PasswordProvider：现有 username/password 校验（默认）
  session_bridge.py   # 会话桥：把「opaque 会话 Cookie」翻译为现有 access/refresh 对
```

1. **Cookie 会话（he_session）**：接入外部身份时，`POST /api/auth/login` 改由外部 IdP 完成认证，回调后由 `session_bridge` 签发 `he_session=<opaque>; HttpOnly; SameSite=Lax`（服务端会话存储）并在换发 access token 时透明兑换。**V2 不实现**，只保留桥的接缝与契约文档（原型「鉴权接入」页展示的 4 行契约即本节内容）。
2. **SSO/OIDC 回调**：注册 `GET /api/auth/callback`，按 `sub` 或 `email` 匹配 `users` 行；未匹配返回 `403 AUTH_NO_MAPPING`，**不自动建号**（不放开注册）。V2 未配置 IdP 时返回 `501 AUTH_PROVIDER_NOT_CONFIGURED`（契约可见、可测、不半成品）。
3. **用户信息映射**：接入后只写 `users`（id/username/display_name/is_active）与 `workspace_members`（空间角色）；业务权限一律以成员关系判定，不信任 IdP 的组信息。

接入后需要改的代码只有三处：`providers.py` 注册新 Provider、`session_bridge` 实现、`/api/auth/callback` 接线——即「极少的改动完成多用户接入」的承诺边界。

### 2.4 权限矩阵（服务端收口）

| 能力 | 全局管理员 | 空间管理员 | 成员 | 只读成员 |
|---|---:|---:|---:|---:|
| 创建工作空间、设置初始额度与初始空间管理员 | ✓ | — | — | — |
| 调整空间额度、上报凭据 | ✓ | ✓ | — | — |
| 添加成员、授予 member/viewer | ✓ | ✓ | — | — |
| 任命/撤销空间管理员、把自己加为空间管理员 | ✓ | — | — | — |
| 配置进化对象（targets CRUD） | ✓ | ✓ | — | — |
| 启动自进化 / 仅聚类 | ✓ | ✓ | — | — |
| 查看总览、Session、bad case、归因、运行历史 | ✓ | ✓ | ✓ | ✓ |
| 触发轨迹同步（admin 手动处理） | ✓ | — | — | — |

实现要点：

- 中间件在现有 `BEARER_AUTH`（产出 `principal`）之后追加空间校验依赖 `require_workspace_role(wid, min_role)`：读 `workspace_members` 判定 `space_admin > member > viewer`；`users.role=admin` 直通所有空间。
- **每个空间作用域端点都必须挂该校验**；前端隐藏入口只是体验护栏（原型同款），不是安全边界。
- 现有全局端点（`/api/users`、`/api/acquisition/sync`、targets 写操作中的 admin 判定）保持 `role=admin` 不变。

## 3. 数据模型

### 3.1 新表 `workspaces`

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | `VARCHAR(36)` | PK | ULID；演示样例 `ws-harness` 等短 id 仅 fixtures 使用 |
| `name` | `VARCHAR(128)` | NOT NULL UNIQUE | 空间名 |
| `mark` | `VARCHAR(255)` | NOT NULL DEFAULT '' | 说明/备注 |
| `quota` | `INTEGER` | NOT NULL | bad case 累计数量上限；创建时设置，之后可调 |
| `status` | `VARCHAR(16)` | NOT NULL DEFAULT 'active' | 预留；V2 只有 `active`（无归档/删除） |
| `created_by` | `VARCHAR(36)` | NULL FK → `users.id` | 创建人（全局管理员） |
| `created_at` / `updated_at` | `DATETIME` | NOT NULL | — |

### 3.2 新表 `workspace_members`

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `workspace_id` | `VARCHAR(36)` | PK 组成, FK → `workspaces.id` ON DELETE CASCADE | — |
| `user_id` | `VARCHAR(36)` | PK 组成, FK → `users.id` ON DELETE CASCADE | — |
| `role` | `VARCHAR(16)` | NOT NULL | `space_admin` / `member` / `viewer` |
| `joined_at` | `DATETIME` | NOT NULL | — |

约束：`UNIQUE(workspace_id, user_id)`（即联合主键）；索引 `INDEX(user_id)`（反查我的空间）。

- 全局管理员**不必**出现在成员表即拥有全部空间权限（§2.4 直通）；「把自己加为空间管理员」会真正写入一行 `space_admin`（审计可见）。
- 一个空间允许多个 `space_admin`；创建空间时 `spaceAdminIds[]` 至少一个（可含创建者自己）。

### 3.3 新表 `workspace_ingest_credentials`

| 列 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | `VARCHAR(36)` | PK | ULID |
| `workspace_id` | `VARCHAR(36)` | FK → `workspaces.id` ON DELETE CASCADE | — |
| `credential_hash` | `CHAR(64)` | NOT NULL | 凭据 SHA-256（凭据是随机 opaque 串，无需慢哈希） |
| `credential_prefix` | `VARCHAR(12)` | NOT NULL | 脱敏展示用前缀（如 `whk_9f2e…`） |
| `created_by` | `VARCHAR(36)` | NULL FK → `users.id` | 创建人 |
| `created_at` | `DATETIME` | NOT NULL | — |
| `last_used_at` | `DATETIME` | NULL | 最近一次上报使用时间（排障） |
| `revoked_at` | `DATETIME` | NULL | 非空即失效 |

- 一个空间可同时持有多条有效凭据（轮换窗口期：先建新、验证、再撤旧）；「轮换」= 新建一条 + 立即撤销其余。
- 明文凭据仅在创建响应中返回一次，不落库、不进日志。

### 3.4 既有表加列

| 表 | 加列 | 约束与索引 | 说明 |
|---|---|---|---|
| `bad_cases` | `workspace_id VARCHAR(36) NOT NULL` | FK → `workspaces.id`；`INDEX(workspace_id, created_at)`、`INDEX(workspace_id, object_name)`、`INDEX(workspace_id, bad_case_type)` | [16](16-v2-overview.md) 总览聚合与 [17](17-v2-attribution.md) 归因范围都走这些索引 |
| `evolution_targets` | `workspace_id VARCHAR(36) NOT NULL` | FK；唯一键改为 `UNIQUE(workspace_id, object_type, object_name)`（替换原全局唯一） | 进化对象配置按空间隔离（原型 `EV_TARGETS` 同款） |
| `evolution_runs` | `workspace_id VARCHAR(36) NOT NULL`；`potential_policy JSON NULL`；`cache_enabled BOOLEAN NOT NULL DEFAULT false` | FK；`INDEX(workspace_id, created_at DESC)` | policy 快照与缓存开关见 [17 §4/§5](17-v2-attribution.md) |
| `evolution_run_events` | `workspace_id VARCHAR(36) NOT NULL` | `INDEX(workspace_id, run_id)` | 事件随 run 带空间，便于空间级审计 |

**不改的表与理由**：

- `session_families` / `agents` / `agent_events` / `user_turns` / `trajectory_payloads` / `source_records` **不加空间列**：轨迹归一化是全局管线；一个空间的 Session 集合定义为「该空间 bad case 涉及的根会话」（投影口径，见 [16 §2](16-v2-overview.md)）。一个 Session 被多个空间上报 bad case 时天然多归属，不需要在轨迹侧二选一。
- `users` 不加空间列：空间角色全部在 `workspace_members`。
- `job_runs` 不加：任务引用的业务对象已带空间，按 `ref_id` 反查。

### 3.5 迁移

- Alembic 单版本：建 3 张新表 → 3 张表加列（`render_as_batch=True` 兼容 SQLite）→ 写入默认空间行（id 固定 `ws-default`，名「默认空间」，quota 取 `COUNT(bad_cases)` 现值 + 余量）→ `bad_cases`/`evolution_targets`/`evolution_runs` 回填 `ws-default` → 全局管理员与现有 users 全部加入默认空间成员（admin 照 §2.4 直通，写入仅为可见性）。
- 运行时配置 `HE_DEFAULT_WORKSPACE_ID=ws-default`：未带空间上下文的内部任务（如目录同步写入）落到该空间。
- **目录同步默认停用**：`bad_case_catalog_sync` 定时任务改为 `HE_BAD_CASE_CATALOG_SYNC_ENABLED=false` 默认关闭；存量链路（[12](12-bad-case-catalog-sync.md)）保留代码，生产以空间上报接口为主通道。`bad_case_root_sync`（轨迹补齐）**保持启用**——上报只是写入 bad case 行，执行流与触发点仍依赖轨迹归一化。

## 4. API 契约

### 4.1 会话与空间

| 端点 | 权限 | 说明 |
|---|---|---|
| `GET /api/auth/session` | 登录 | §2.2 的 user + workspaces 聚合 |
| `GET /api/workspaces` | 登录 | 我可见的空间：普通用户=所在空间；全局管理员=全部空间（含未加入，标 `role=space_admin`） |
| `POST /api/workspaces` | 全局管理员 | `{name, mark, quota, spaceAdminIds[]}`；`spaceAdminIds` 至少 1 人且均为已有用户（可含全局管理员自己）；`409 WORKSPACE_EXISTS`、`422 QUOTA_INVALID`（<0）、`422 ROLE_INVALID`（列表含不存在用户） |
| `PUT /api/workspaces/{wid}` | 全局管理员或空间管理员 | 全局管理员可改 `name/mark/quota`；空间管理员仅可改 `quota` 且 `quota >= used`；越权字段 `403 WORKSPACE_FORBIDDEN`、`422 QUOTA_INVALID` |
| `GET /api/workspaces/{wid}/members` | 空间成员 | `{items: [{userId, username, displayName, role, joinedAt}]}` |
| `POST /api/workspaces/{wid}/members` | 全局管理员或空间管理员 | `{userId, role}`；空间管理员只能授 `member/viewer`（授 `space_admin` → `403 WORKSPACE_FORBIDDEN`）；`409 MEMBER_EXISTS` |
| `PUT /api/workspaces/{wid}/members/{userId}` | 同上 | 改角色；空间管理员不能改 `space_admin` 行（含自己被全局管理员任命的情况）；`409 ROLE_LOCKED` |
| `DELETE /api/workspaces/{wid}/members/{userId}` | 同上 | 移除成员；移除后该用户失去空间可见性；`space_admin` 行仅全局管理员可移除 |
| `POST /api/workspaces/{wid}/members/self-admin` | 全局管理员 | 把自己写入 `space_admin`（幂等；已存在则更新角色） |
| `POST /api/workspaces/{wid}/credentials` | 全局管理员或空间管理员 | 轮换：创建新凭据并立即撤销其余 → `201 {credentialId, credential, prefix}`（明文仅此一次） |
| `DELETE /api/workspaces/{wid}/credentials/{cid}` | 同上 | 撤销单条；`404 CREDENTIAL_NOT_FOUND` |
| `GET /api/workspaces/{wid}/credentials` | 同上 | 脱敏列表（prefix/created/lastUsed/revoked） |

- `role` 封闭集合：`space_admin | member | viewer`；请求携带其它值 `422 ROLE_INVALID`。
- 全局管理员的成员操作走同一组端点（无单独管理面），符合「管理员可以添加其它成员和给管理员以下的权限」。

### 4.2 bad case 上报接口

```text
POST /api/workspaces/{workspaceId}/bad-cases
Authorization: Bearer <workspace credential>     # 空间凭据，不是用户 JWT
Content-Type: application/json
```

请求体即 `bad_cases` 表类型（camelCase DTO，与 [05 §3.4](05-api-design.md) 的 `BadCase` 同源）：

```json
{
  "badCaseId": "BC-HC-0001",
  "sessionId": "cb819c5b-286f-4eab-a681-4ba5414b844d",
  "badCaseType": "self",
  "objectName": "deep-research",
  "objectType": "skill",
  "objectVersion": "v2.0.0",
  "badCaseAgentId": null,
  "title": "检索索引读取失败",
  "reason": "deep-research skill 自身执行时检索索引读取失败：ENOENT apps/server/src/search/index.ts:142",
  "metaData": { "file": "apps/server/src/search/index.ts", "line": 142, "error": "ENOENT" },
  "source": "ci-reporter",
  "createdAt": "2026-11-11T10:20:30+08:00"
}
```

- `badCaseId` 可选：携带时按主键 **upsert**（幂等重报，更新全部上游字段、不重复计数）；缺省由服务端生成（`BC-<ws前缀>-<序号>`）。
- 必填：`sessionId`（36 位根会话 ID）、`badCaseType`、`objectName`、`objectType`、`title`（≤255）；`reason` 缺省取 `title`。
- **空间身份只从 URL + 凭据解析**，不信任 body 里的任何空间信息（无该字段）。
- 鉴权顺序：凭据无效 → `401 CREDENTIAL_INVALID`；空间不存在 → `404 WORKSPACE_NOT_FOUND`；凭据已撤销 → `401 CREDENTIAL_INVALID`。
- **额度**：`COUNT(bad_cases WHERE workspace_id=wid) >= quota` 时新插入返回 `409 QUOTA_EXCEEDED`（`details: {quota, used}`）；不自动丢弃旧数据；upsert 已存在的 `badCaseId` 不占新额度。
- 成功 `201 {badCaseId, workspaceUsed}`；响应头 `X-HE-Workspace-Used` 同值（脚本友好）。
- 上报成功后自动触发既有 `bad_case_root_sync`（[11](11-bad-case-session-sync.md)）补齐该根会话轨迹——上报本身不要求轨迹已存在，触发点坐标在归一化后才可用（[17 §3](17-v2-attribution.md)）。

### 4.3 新增错误码

| code | HTTP | 触发场景 |
|---|---|---|
| `WORKSPACE_NOT_FOUND` | 404 | 空间不存在（或对当前用户不可见，避免枚举） |
| `WORKSPACE_FORBIDDEN` | 403 | 已登录但对该空间无所需角色 / 空间管理员越权字段 |
| `WORKSPACE_EXISTS` | 409 | 同名空间已存在 |
| `MEMBER_EXISTS` | 409 | 该用户已是空间成员 |
| `ROLE_INVALID` | 422 | 角色值非法（含 `POST /users` 创建 admin、初始管理员列表含不存在用户） |
| `ROLE_LOCKED` | 409 | 空间管理员试图修改/移除 `space_admin` 行 |
| `CREDENTIAL_NOT_FOUND` | 404 | 凭据不存在 |
| `CREDENTIAL_INVALID` | 401 | 上报凭据缺失/错误/已撤销 |
| `QUOTA_EXCEEDED` | 409 | 空间 bad case 数量达到额度上限 |
| `QUOTA_INVALID` | 422 | 额度 < 0 或小于当前已用量 |
| `AUTH_NO_MAPPING` | 403 | SSO 回调按 sub/email 匹配不到用户（不自动建号） |
| `AUTH_PROVIDER_NOT_CONFIGURED` | 501 | IdP 未配置时访问 `/api/auth/callback` |

## 5. 服务端实现（代码改动地图）

按 [01 §3](01-architecture.md) 的分层落位：

| 改动 | 位置 | 内容 |
|---|---|---|
| 新增服务 | `service/workspaces/`（service/repository/schemas） | 空间/成员/凭据/额度的业务规则；`used` 一律 `COUNT(bad_cases)` 实时聚合（不物化，理由同 [06 §3.2](06-database-design.md) 问题数不落列） |
| 新增路由 | `api/workspaces.py`、`api/ingest.py` | §4.1 与 §4.2 端点；上报端点用独立的 `CREDENTIAL_AUTH` 依赖（不消费 Bearer JWT） |
| 鉴权扩展 | `middleware/`（或 `api/security.py`） | `require_workspace_role(wid, min_role)` 依赖；`RequestContext.principal` 不变 |
| identity 接缝 | `service/identity/providers.py` + `session_bridge.py` + `api/auth.py` | §2.2/§2.3：`GET /auth/session`、AuthProvider 协议、callback 占位 |
| 建号收紧 | `service/identity/service.py` | `create_user` 拒绝 `role=admin` |
| 既有路由空间化 | `api/sessions.py`、`api/problems.py`、`api/evolution_*.py`、`api/catalogs.py` | 全部挂 `require_workspace_role` 并把 `workspace_id` 下推到查询（路径见 [16 §5](16-v2-overview.md)、[17 §7](17-v2-attribution.md)） |
| 迁移 | `alembic/` | §3.5 |
| fixtures | `fixtures/` + `app/cli.py seed` | 3 个演示空间（对齐原型 ws-harness/ws-agent/ws-research）+ 成员 + 凭据 + 额度；`pnpm fixtures:check` 同步 |

测试要点：权限矩阵逐格（全局管理员/空间管理员/成员/只读 × 各端点）；凭据轮换窗口期两条凭据并存可用、撤销后 401；额度边界（=quota 拒绝、upsert 不计增量、调低额度至 used 之下 422）；`require_workspace_role` 对不可见空间统一 404。

## 6. 前端（代码改动地图）

| 改动 | 位置 | 内容 |
|---|---|---|
| 启动取数 | `stores/auth.ts` | 登录/刷新后调 `GET /auth/session`，保存 `user + workspaces + currentWorkspaceId`（持久化到 localStorage，用于旧路由重定向） |
| 顶栏 | `components/layout/TopNav.vue` | 空间切换器（名称 + used/quota + 我的角色；切换即换路由前缀并清 query 缓存）；用户菜单保留 |
| 路由 | `router/` | 新前缀 `/workspaces/:workspaceId/...`；旧 `/sessions/**`、`/evolution/**` 重定向（§7）；空间守卫：不在 `workspaces` 内跳空间选择页 |
| queryKey | `api/queryKeys.ts` | **全部业务 key 加 `workspaceId` 首段**，切换空间不复用旧空间缓存（失效规则同 [08 §2.4](08-frontend-implementation.md)） |
| 空间管理页 | `pages/workspaces/Admin.vue` | 四 Tab：空间与额度 / 成员与角色 / 上报接入（地址+凭据+curl 示例+额度）/ 鉴权接入（§2.3 契约展示，只读） |
| 登录页 | `pages/login/*` | 保持表单；页脚加鉴权接入说明文案（对应原型登录页脚注） |

空间选择页（无 `currentWorkspaceId` 时）：列出 `workspaces` 卡片，点击进入；不静默选择第一个空间（[design-v2 §10](../ui-prototype-v2/design-v2.md) 同款）。

## 7. 兼容与迁移

- **旧路由**：`/sessions/**`、`/sessions/:sid/errors*`、`/evolution/**` → 按「最近访问且有权限的空间」重定向到 `/workspaces/:wid/...`；解析不到进空间选择页。旧 `?issue=` 深链先解析到 bad case 再重定向（[17 §11](17-v2-attribution.md)）。
- **契约**：新增端点与 `BadCase.workspaceId` 等字段进 OpenAPI，跑 `pnpm contract:generate`；`packages/contracts` 生成物更新，前端只 import type（不变流程）。
- **存量数据**：按 §3.5 回填默认空间；生产 `8.149.232.63` 当前无数据，可在线上直接执行迁移。
- 上报脚本迁移：从「写 trajectory_payloads 的第三方脚本」之外，新增 bad case 直报路径；两者不冲突（轨迹写入链路不变）。

## 8. 测试与验收

- 登录后 `GET /auth/session` 返回 user + workspaces；普通用户只见到自己空间。
- 全局管理员创建空间（额度 + 初始管理员多选）→ 空间管理员可调额度/管成员/配对象/启动自进化 → 成员只读路径 403。
- 上报：curl 带凭据 POST body=bad_cases 类型 → 201；重复 badCaseId upsert；额度满 409；错误凭据 401。
- 切换空间后所有列表数据隔离（无串空间行）。
- `pnpm test:api` 权限矩阵用例 + `pnpm test:e2e -- --pattern workspaces` 冒烟。

## 9. 非目标

- 空间删除/归档与数据清算；空间级配额计费或通知。
- 公开注册、邀请链接、密码自助重置。
- 空间级 SSO 隔离（IdP 按空间分租户）——接入层按用户映射，空间授权仍由成员表判定。
- 审计日志表（`workspace_members` 变更历史）——依赖 `updated_at` 与 git/PR 记录，后续需要再加。
- `GET /api/workspaces/{wid}` 单空间详情端点——列表 + `auth/session` 已覆盖消费场景。

## 10. 已确认决策

| # | 决策 | 依据 |
|---|---|---|
| W1 | 身份栈不变（JWT + refresh cookie），鉴权接入=Provider 协议 + 会话桥 + callback 占位，V2 不切换默认 | 「预留接入接口，极少改动即可接入」的目标态 |
| W2 | 空间 Session 集合 = 空间 bad case 涉及的根会话（投影），轨迹表不加空间列 | 轨迹管线全局共享；Session 天然多归属 |
| W3 | `used` 实时 `COUNT` 聚合，不物化 | 与 bad case 计数同理由（[06 §3.2](06-database-design.md)），额度非热点路径 |
| W4 | 上报凭据是独立 opaque Bearer，与用户 JWT 并存且用途分离 | 上报方是脚本/CI，不是登录用户 |
| W5 | 全局管理员唯一，`POST /users` 禁建 admin；「自任空间管理员」仅全局管理员可用 | 目标态第 1/2 点；防自我提权 |
| W6 | 目录同步默认停用，空间上报接口为主通道；根轨迹补齐保持启用 | bad case 来源收敛；触发点仍依赖归一化 |
| W7 | 不做空间删除/归档 | 原型无入口；数据清算复杂度高收益低 |
