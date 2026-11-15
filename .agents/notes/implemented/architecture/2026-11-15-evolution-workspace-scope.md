# Agent Note: 进化对象的空间归属与票据边界

Status: implemented

[English](2026-11-15-evolution-workspace-scope.en.md) | 中文

## Problem

m7-02 给 `evolution_targets`、`evolution_runs` 与 `evolution_run_events` 加了 `workspace_id`，并把对象唯一键改成含空间的三元组，但读取与服务层仍按全局处理：对象列表能列出所有空间，同名对象无法在两个空间各配一份，run 列表、详情、重试、步骤与事件只按 run id 查找，SSE 票据只校验 run 是否存在且活跃。结果是任何一个登录用户只要拿到另一个空间的 run id，就能读详情、拉事件甚至订阅 SSE；向导预览与 run 准备按对象名全局查 bad case，也会把别的空间数据带进本空间的 run。目标的旧唯一键改成三元组后，冲突识别仍写着旧约束名，重复对象会落到 500。

## Decision

- `workspace_id` 是进化资源的唯一归属列：target、run、event 都从它判定可见性，不另建映射表。target 的唯一性由 `(workspace_id, object_type, object_name)` 承担，仓储层所有读写都接受可选的 `workspace_ids` 过滤，未传表示显式全局（仅全局管理员路径使用）。
- V2 路由落在 `/api/workspaces/{wid}/evolution/**`：targets、runs、steps、run events、retry、cluster previews、launch，以及本空间 targets/models 清单。读要求 `viewer`，写（target CRUD、launch、cluster preview、retry）要求 `space_admin`；全局管理员沿用依赖直通。路径空间同时约束资源归属，跨空间资源按 404 处理，不暴露存在性。
- 旧无前缀路由保留一个版本并按调用者可见空间过滤：全局管理员不设过滤，其余用户传 `WorkspaceService.visible_ids`。旧 CSRUD 维持全局管理员写权限；旧 launch/retry 先解析目标或 run 的所属空间，再按 `space_admin` 授权，这样成员与只读成员不能借旧路径写入。
- 旧 launch 不携带空间，按 `(object_type, object_name)` 在可见空间内解析；同名配置只命中一条时直接使用，多条时优先默认空间，仍不唯一则返回 `409 TARGET_NOT_CONFIGURED`，不在多个空间之间猜。
- run 的写入链从 target 快照空间：创建 run 时写入 `workspace_id`，probe hit 查询与 prepare 关联都带 `(run.workspace_id,)`，事件 append 从 run 行继承空间，避免调用方另行传参造成不一致。
- `POST /api/events/ticket` 接受可选 `workspaceId`。携带时先证明该空间成员关系，再要求每个 topic 的 run 属于该空间；未携带时逐个 run 校验其空间成员关系，兼容旧客户端但不放松边界。失败统一返回 `401 TICKET_INVALID`，不区分空间不存在、无权与 run 不可订阅。
- 清单沿用同一空间视图：旧 `/api/catalogs/**` 按可见空间过滤，V2 增加 `/api/workspaces/{wid}/catalogs/**`。模型清单从该空间 bad case 投影出的 Session 聚合 `agents.model`，不再返回全库模型。

## Alternatives considered

- **只给旧端点加过滤，不新增 V2 路由**：m7-08 的前端空间壳与后续向导已经按 `/workspaces/{wid}/evolution/**` 设计，若本轮不落路由，后续 issue 要回头改 API 与契约；且旧端点没有空间上下文，无法表达空间管理员写权限。
- **把旧 launch/retry 一律收成全局管理员**：实现最省事，但会直接打断现有空间管理员的 V1 页面，也违反“空间管理员拥有本空间操作权”的验收。
- **SSE 只按 run id 授权**：run id 不可猜测不是授权，泄露的链接仍可订阅；票据必须带可证明的空间关系。把 `workspaceId` 设为必填会打断旧前端，因此保留可选并在服务端逐 run 兜底。
- **在事件表里信任调用方传入的空间**：事件空间必须由 run 行派生，否则一次错误的调用就能把事件写进别的空间并影响票据过滤。
- **为跨空间资源返回 403**：会暴露资源存在性，与 m7 统一的不可见空间 404 语义冲突。

## Consequences

- 既有集成测试里“成员看到与管理员相同列表”的假设不再成立：成员必须先在空间内有成员行；迁移只为迁移时已存在的用户补了默认空间的 viewer 行，此后创建的用户由空间管理员显式加入。
- 旧无前缀路径只是兼容层，写入口仍限全局管理员；空间管理员与前端应使用 V2 路径。旧 launch 在同名跨空间配置下会拒绝，而不是替调用者选择空间。
- 事件表新增空间列已有迁移与索引；本轮只补写入与票据校验，没有新增迁移。
- 后续知识库对象与归因预览沿用同一模式：资源带空间、路由带 `{wid}`、票据带空间证明；`workspaceId` 的可选兼容分支在旧前端退场后可以收紧为必填。
