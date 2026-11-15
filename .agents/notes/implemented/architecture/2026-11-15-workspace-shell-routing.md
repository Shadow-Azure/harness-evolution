# Agent Note: 前端空间壳、路由守卫与缓存隔离

Status: implemented

[English](2026-11-15-workspace-shell-routing.en.md) | 中文

## Problem

m7-04 到 m7-07 把后端的 Session、bad case、自进化对象、运行和 SSE 都按空间隔离了，但 Web 端仍停在 V1：路由是 `/sessions/**` 与 `/evolution/**`，启动时先 `refresh` 再 `me`，query key 以资源 id 开头，页面从不携带 `wid`。结果是前端只能继续调用“用户全部可见空间并集”的兼容端点；同一张 Session 卡在不同空间看到的是同一份缓存，切换空间没有稳定的空间上下文，旧深链也无法判断应该落到哪个空间。

## Decision

- 路由壳：新增 `/workspaces/:wid` 父路由，Session 列表、会话概览、错误详情、自进化列表、运行详情、仅聚类预览与对象配置都挂在其下；`/workspaces` 是空间选择页。`/workspaces/:wid` 的默认子页暂时是 `sessions`，等 m8-04 的总览页落地后再改为 `overview`。
- 守卫：`beforeEach` 先恢复 `auth/session`，未登录跳 `/login?redirect=…`，强制改密只放行登录与改密页；进入空间路由时要求 `wid` 在当前用户可见空间内，否则回选择页并带 `reason=forbidden`。`/`、`/sessions/**`、`/errors`、`/evolution/**` 视为旧路由，按“localStorage 最近访问且仍可见 → 唯一可见空间 → 选择页”的顺序解析，重定向使用 `replace`，只发生一次并保留 query/hash。
- 启动：`tryRefresh` 从 `refresh` 改为“refresh + `GET /auth/session`”，一次性拿到 `user` 与 `workspaces`；登录、改密成功后也重取同一 payload，避免 `me` 与空间列表来自不同时刻。
- 缓存：`queryKeys` 全部以 `["ws", wid]` 开头；Session、bad case、运行、step、事件、对象、catalog 的读取改走 `/api/workspaces/{wid}/...`。切换空间时失效旧 `["ws", oldWid]` 整棵，并把 `RouterView` 的 key 设为 `wid`，让页面 `ref` 状态随空间重建；切换目标丢弃上一空间拥有的 `sessionId` / `runId`，只保留分区（Session 列表或自进化列表）。
- bad case 详情改走空间端点；分析投影仍由兼容端点提供（m7-06 已按可见空间收口），前端用返回的 `sessionId` 再校验一次路由归属，不匹配按 `409` 处理。
- 顶栏：新增 `WorkspacePicker`（名称、角色、used/quota、成员数），切换时保留当前分区并写路由；用户菜单补当前空间与角色。数据同步按钮的失效范围改为当前 `wid` 的 Session 前缀。

## Alternatives considered

- **保留旧全局 query key，只在页面 props 里带 `wid`**：缓存仍会跨空间命中，E2E 的“切空间后旧 query 不命中”无法成立；拒绝。
- **旧深链静默取第一个可见空间**：多空间用户会看到错误空间的数据，设计明确禁止；解析失败进选择页。
- **每个页面各自读 `route.params.wid` 并各自拼 URL**：链接和缓存 key 容易漏 `wid`；统一 `useWorkspaceId`、`workspacePath` 与 query key 工厂。
- **在 bad case 空间端点之外继续传 `sessionId` 让旧端点做归属校验**：空间端点不认这个参数，跨 Session 会静默成功；改为前端比对返回的 `sessionId`，把边界留在可见 UI 行为里。
- **切空间时保留完整子路径**：`/sessions/:sid` 的 id 属于旧空间，直接带到新空间只会得到 404；只保留分区。

## Consequences

- `auth/session` 的 `used` 聚合读取外部引导的 `bad_cases` 表；全新部署必须先完成外部表初始化，否则空间壳启动会停在登录页。
- 默认落地页暂时是 Session 列表而不是设计里的总览；m8-04 补页面时只需改 `DEFAULT_WORKSPACE_PATH` 与守卫的目标。
- 分析/探针仍只有一个按“全部可见空间”过滤的兼容端点，空间级归因端点落地前，前端只能用 `wid` 做缓存隔离，不能阻止同一归因在多个可见空间被打开。
- 可见空间被移除而浏览器仍停在旧 URL 时，守卫会回选择页；API 侧返回 `404 WORKSPACE_NOT_FOUND` 时页面显示错误态，不做静默换空间。
- 旧路由兼容层只保留一个迁移版本；删除前需要先确认书签、E2E 与外部上报链接都不再使用无 `wid` 路径。
