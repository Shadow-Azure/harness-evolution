# Agent Note: 归因 Skill 不可变版本与三级绑定

Status: implemented

[English](2026-11-17-attribution-skill-registry.en.md) | 中文

## Problem

归因方法若只由全局引擎开关或对象上的可变正文决定，两个对象无法安全选择不同方法，配置更新还会改变历史 Run 与缓存的含义；平台默认、空间默认和对象覆盖也缺少明确优先级。

## Decision

归因 Skill 分为 definition、append-only revision 与 binding：revision 固化受控 JSON 内容、SHA-256、executor type 和输出 schema，binding 只引用已发布且兼容的 revision。解析顺序固定为对象绑定、空间默认、受保护的平台默认；解绑用于回退，绑定旧 revision 即回滚。平台默认由迁移播种且不能经空间 API 停用。Run 创建时固化实际生效的 key、revision 与 content hash，报告执行清单使用该快照而不是读取当前绑定。

## Alternatives considered

把 Skill 正文直接写进进化对象会混合目标代码配置与归因策略，并使每次编辑覆盖历史，因此否决。只保存当前 revision 指针会让旧 Run 随绑定漂移，因此 Run 必须保存有效身份。允许上传可执行代码会扩大供应链和密钥边界，本阶段只保存说明、流程与工具声明，由平台执行器解释。

## Consequences

不同对象可独立绑定 revision，空间可设统一回退，未配置时仍有确定的平台默认；停用只影响未来解析，历史报告与 Run 保持可读。Skill key 当前全平台唯一以简化跨空间引用保护，若未来需要同名空间 Skill，应把唯一身份升级为 namespace/key 且保持清单 key 稳定。执行器仍是规则引擎，`agent_stub` 与 `agent` 仅作为注册元数据，真实调用由后续执行器迭代交付。
