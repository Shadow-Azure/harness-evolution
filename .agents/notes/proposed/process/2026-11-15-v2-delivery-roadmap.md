# Agent Note: V2 交付路线图与真实轨迹证据门禁

Status: proposed

[English](2026-11-15-v2-delivery-roadmap.en.md) | 中文

## Problem

PR #209 已确认 V2 目标态，但流程树没有实现切片；真实 Session ccbdb2f0 又显示语义版本缺失、父子关系导出不一致、根会话停在 tool_use、知识库文档触发未建模。若直接进入潜在匹配，数量与归因证据会建立在不可靠的 Session 关联上。

## Decision

M6 以已交付的接入基座和运行证据收口，新增 M7–M12：M7–M11 交付空间权限、空间数据面、Session 证据、归因管线与多归因切换，M12 承接真实上游、外部契约、patch/评测、聚类升级和平台质量欠账。M9 作为 M10 的硬门禁，负责对象 revision、关系置信度、执行完成度、触发坐标和 knowledge 文档触发；PotentialMatcher、归一化页面与七步 run 只能消费这些证据。

## Alternatives considered

把证据修正塞进原 M9 归因阶段会让一个 milestone 同时承担数据修复与业务闭环，失败时无法判断数量错误来自版本、关系还是归因；把知识库触发并入普通 Read 会把源码浏览误判为知识库使用；继续使用 object_version 单一口径会漏掉只有内容 digest 的真实 Skill。

## Consequences

流程对象从 4 个 V2 阶段扩为 5 个，M9 的所有 P0 完成前不得启动 M10 潜在匹配；M6 未兑现的工作迁成 M12 新 issue，旧 GitHub issue 只作为迁移记录关闭并回链。真实附件只用于脱敏 fixture 设计，不进入仓库；知识库文档先作为证据对象，是否成为可自进化目标由后续实现边界决定。
