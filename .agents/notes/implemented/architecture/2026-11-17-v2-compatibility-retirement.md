# Agent Note: V2 兼容面退役条件与文档收口

Status: implemented

[English](2026-11-17-v2-compatibility-retirement.en.md) | 中文

## Problem

V2 已把工作空间、凭据上报、总览、多归因与七步运行落成默认路径，但常驻文档仍停在 V1：`docs/architecture.md` 写单组织、只读归因与六步，`plans/fullstack-design/README.md` 还把 architecture 同步留成欠账；V1 读端点、无空间路由、legacy run 与可空列仍在运行，却没有共同的版本触发和机械删除条件。继续拖延会让“兼容多久”靠记忆决定，删除时也容易漏掉前端死代码、契约类型、测试与文档。

## Decision

- 删除触发版本定为 V3，即 V2 之后的第一个主版本；V2 兼容窗口内保留全部 V1 面，只记录条件，不提前删端点、路由、字段或迁移。
- 新增 [compatibility.md](../../../../docs/compatibility.md) 作为兼容面、触发版本与机械清单的唯一 home；`docs/architecture.md` 与 `docs/development.md` 只链接，不复制清单。
- 常驻文档按实现重写：工作空间与角色、凭据上报、空间 Session 与总览、多归因、四步向导、七步运行与 lane DAG、证据分级/执行闭环/知识触发成为当前事实，V1 兼容面单列为边界。
- 同步设计 Note：[workspace-shell-routing](2026-11-15-workspace-shell-routing.md)、[attribution-read-api](../feature/2026-11-17-attribution-read-api.md)、[multi-attribution-error-detail](../feature/2026-11-17-multi-attribution-error-detail.md) 的“m11-06 退役”表述改为指向 V3 清单。
- 同步 `plans/fullstack-design` 的设计入口：README 的“待同步”欠账改为已同步，15 §7 的兼容步骤指向 compatibility。
- 本 PR 不改代码、契约、迁移或测试，兼容行为与用户可见行为保持不变。

## Alternatives considered

- 现在删除 V1 端点与路由：会破坏旧书签、外部上报客户端和兼容页，也违反 issue 的非目标；拒绝。
- 无限期保留兼容层：没有机械退出条件，架构长期背双路径；拒绝。
- 把清单写进 architecture：会超词数预算并让 architecture 承担步骤型内容；拒绝，按“现状→architecture、步骤→development/compatibility”分层。
- 直接把可空列收紧为 NOT NULL：存量 V1 行可能没有 probe 或 cache key，迁移不安全；拒绝，先回填再收紧。
- 只改 plans 不改常驻文档：plans 不是常驻事实 home，读者仍会看到 V1 描述；拒绝。

## Consequences

- V2 期间保留双路径测试与契约成本；V3 按 compatibility 清单一次性清理。
- V3 删除前必须确认无调用、无旧链接、无 legacy run 读取且可空列已回填，否则继续保留。
- 兼容面变化要同时更新 compatibility、architecture 链接与 owning Note；一个事实一个 home。
- 本次不产生用户可见行为变化，验证以 docs/flow/契约门禁为准。
