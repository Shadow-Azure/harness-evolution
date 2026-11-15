# Agent Note: Session 与 bad case 读路径空间化

Status: implemented

[English](2026-11-15-session-bad-case-workspace-scope.en.md) | 中文

## Problem

m7-03 给请求装上了空间门禁，m7-05 给了空间管理与上报凭据，但 Session 与 bad case 的读路径仍只看“库里有没有这行”。前端只要换一个 `sessionId` 或 `badCaseId`，就能读到别的空间上报的问题；同一个根会话被两个空间分别上报时，两侧也会看到对方的 bad case。轨迹表本身是全局共享的，不会也不应该加 `workspace_id`，所以“这条 Session 属于哪个空间”只能由 bad case 的上报归属反推，不能靠前端路由兜底。

## Decision

- 新增 `WorkspaceReadScope`（`db/crud/read_scope.py`）作为唯一可见性口径：`for_workspace(wid)` 固定一个已授权空间，`for_user(userId)` 展开为成员表子查询，`all_workspaces()` 只给全局管理员。没有默认构造，避免漏传 scope 时静默放开。
- Session 集合一律由 `bad_cases.workspace_id` 投影得到：列表条件、概览、Agent 树、问题列表都先要求 `session_families.id IN (该 scope 的 bad_case_session_id)`，再叠加原有过滤。未命中的 Session 在列表里不出现，直连时统一 `404 SESSION_NOT_FOUND`；空间不可见同样是 `404 WORKSPACE_NOT_FOUND`，不区分“存在但无权”。
- 新增 V2 路由：`GET /api/workspaces/{wid}/sessions`、`/{sid}`、`/{sid}/tree`、`/{sid}/bad-cases` 与 `/bad-cases/{badCaseId}`，全部挂 `require_workspace_role(wid, viewer)`；固定空间后，同一根会话只返回本空间上报的 bad case，问题详情越界返回 `404 BAD_CASE_NOT_FOUND`。
- V1 旧端点保持路径与 DTO 不变，只把可见性换成“当前用户全部可见空间”的并集：普通用户走成员子查询，全局管理员看全部。`GET /api/workspaces/{wid}/sessions` 本轮仍是 `{items}` 与 V1 同口径过滤，latest-ten 的 `total/pendingSessions` 语义留给 m8-02。
- `probe_reports` 还没有 `workspace_id`（0015 归因迁移尚未落地），因此探针读取按“所属 Session 是否可见”继承边界：`/api/probes/{id}` 与 `/api/sessions/{sid}/probes` 都先过投影，不伪造空间列。
- `bad_cases` 是外部引导表，安装尚未上报时可能不存在。仓储在首次读取时探测表是否存在，缺失时返回空投影（列表为空、直连 404），不让整个 Session 页 500；探测到存在后按仓储实例缓存，不做每请求元数据查询。

## Alternatives considered

- **在轨迹表加 `workspace_id`**：同一根会话可能被多个空间引用，加列就得在同步管线里做归属仲裁，还会把全局归一化拆成按空间复制；设计明确把 Session 当投影而非独立实体。
- **每个查询各写一遍 `IN (SELECT …)`**：列表、概览、树、问题、探针共六处，漏一处就是越权；抽成 `WorkspaceReadScope.condition()` 后每个读路径只声明一次 scope。
- **不可见空间返回 403、不可见 Session 返回 404**：403 会暴露“这个空间存在”，用户可枚举空间 id；统一 404 与设计中的“不可见空间”一致。
- **旧端点直接删掉，只留 V2 路由**：现有前端页面与 E2E 还在调用无前缀路径；冻结保留一个版本并加空间过滤，比同时改两侧风险小。
- **本轮顺手把 latest-ten 的 `total/pendingSessions` 也加上**：会与 m8-02 的筛选语义重复，且搜索改成 root session ID 精确匹配属于那份 issue 的验收；本轮只做空间约束。

## Consequences

- 没有任何 bad case 的 Session 不再出现在列表，也无法直连；这是“空间 Session 集合 = 空间 bad case 根会话投影”的直接后果，需要先有上报或目录同步才能看到会话。
- 全局管理员在旧端点看到全部空间，等价于未过滤；空间管理员只看到自己加入的空间，成员变更下一次请求生效。
- 每次旧端点读取多一个成员子查询（`workspace_members` 上有 `(workspace_id, user_id)` 主键/索引方向），树与问题读取仍在单事务快照内完成。
- 探针的边界只到“Session 可见”这一层；等 0015 给 `probe_reports` 补上 `workspace_id` 后，应按归因归属收紧到空间级。
- `WorkspaceReadScope` 的三种模式没有运行时互斥校验；新增读路径必须显式选一种，不允许 `None` 直接透传为“全部”。
