# Agent Note: 空间归因 Skill 包与执行 revision 分层管理

Status: implemented

[English](2026-11-18-attribution-skill-package-admin.en.md) | 中文

## Problem

内网归因能力以含 `SKILL.md` 和辅助文件的目录交付，但已有归因 Skill registry 面向可执行 revision、Golden 评测和对象绑定，既不能保存完整目录，也不能让空间管理员查看与回收上传资产。直接把任意上传包注册成可执行 revision 会把资产管理入口变成绕过质量门禁的生产发布入口；只把文件放在磁盘又会缺少空间关系、上传者和当前选择状态。

## Decision

- 新增独立的空间 Skill package 资产层：数据库保存包名、上传者、文件数、ZIP 大小、hash、相对路径、`SKILL.md` 与单一生效绑定；文件按 `attribute/{workspace_id}/{package_id}` 隔离存储。
- `attribute-badcases.md` 是不可删除的默认提示词源，API 把它投影为 `attribute-badcases` 虚拟包并按需生成 ZIP；空间没有自定义绑定或删除生效包时回退该默认包。
- 上传包必须低于压缩/展开大小和文件数上限，只能包含一个 UTF-8 `SKILL.md`，其 frontmatter `name` 是空间内唯一身份；拒绝绝对路径、`..`、盘符、符号链接和加密成员。
- viewer 可查看提示词和下载；只有 space admin 或 global admin 可上传、设为生效和删除。上传后保持未生效，管理员显式确认切换。
- package 的生效状态只服务于空间资产配置，不自动创建或绑定现有可执行 revision；生产 Run 仍按 registry 的 Golden 晋级与固化 revision 规则运行。

## Alternatives considered

- **把 ZIP 内容直接写入 `attribution_skill_revisions.content` 并自动绑定**：拒绝。完整目录不适合 JSON revision，且自动绑定会绕过 Golden 评测。
- **只存 ZIP BLOB**：拒绝。大二进制会扩大事务和备份，下载与提示词读取也要反复解压；数据库只保留可查询元数据和提示词快照。
- **上传后立即生效**：拒绝。空间管理员应先检查包名、文件统计和提示词，错误上传不能改变当前配置。
- **允许覆盖同名包**：拒绝。隐式覆盖会让当前选择与下载内容在无 revision 的情况下变化；当前流程要求先删除再上传。

## Consequences

- 空间管理增加“归因 Skill”页签和一组 Bearer/RBAC API，默认包保证每个空间始终能展示一个有效提示词。
- 文件系统成为包内容真值，数据库成为元数据和选择真值；数据库写入失败会清理解压目录，删除先清记录与绑定再尽力清理目录。
- 生产执行与资产配置暂时是两条显式链路。后续内网 adapter 接入时，需要在通过评测的 package 与 immutable revision 之间增加受控发布步骤，而不是复用当前“设为生效”动作。
- ZIP 下载由服务器从已校验目录重新生成，不回传服务器路径；默认包也遵循相同下载形态。
