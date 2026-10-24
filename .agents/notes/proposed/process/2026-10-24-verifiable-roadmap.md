# Agent Note: 可验证路线图与远端同步策略

Status: proposed

[English](2026-10-24-verifiable-roadmap.en.md) | 中文

## Problem

旧路线混合已裁撤时间线，依赖顺序把鉴权放在数据库前，多数 issue 无法独立验收；同时 `flow:sync` 不发布详细正文也不清理远端旧对象。

## Decision

采用 6 个新 milestone、41 个带稳定 id 与 depends 的 issue；实现取舍统一指向 `plans/fullstack-design`；issue 强制包含实施、验证、验收和门禁章节；GitHub 同步完整中文正文；`--retire-missing` 只关闭而非删除不在新树的开放对象。本地 Claude 数据仅用于 SQLite 导入验收，仓库自动门禁使用合成 fixtures。

生成流程实例前，`plans/fullstack-design` 的 6 个 review 问题已在 2026-10-24 固化为 D16–D19 等决策；`05 §10` 只作为本服务客户端契约用于 mock 联调，不表示真实上游已承诺。

## Alternatives considered

保留旧 M1 并追加新阶段会继续让 scope 漂移；物理删除远端 issue 会破坏 #10/#17 等提交追溯；继续用草案表格而不流程实例无法被 scope 和状态机约束。

## Consequences

需要一次性迁移 GitHub milestone/issue 并关闭旧开放对象；后续新增 issue 必须提供依赖与独立验证；真实数据验收只能在本地或受控环境执行。
