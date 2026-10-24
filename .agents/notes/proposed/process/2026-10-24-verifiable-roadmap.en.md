# Agent Note: Verifiable roadmap and remote sync policy

Status: proposed

English | [中文](2026-10-24-verifiable-roadmap.md)

## Problem

The legacy roadmap混合已裁撤时间线，依赖顺序把鉴权放在数据库前，多数 issue 无法独立验收；同时 `flow:sync` 不发布详细正文也不清理远端旧对象。

## Decision

Adopt 6 个新 milestone、41 个带稳定 id 与 depends 的 issue；实现取舍统一指向 `plans/fullstack-design`；issue 强制包含实施、验证、验收和门禁章节；GitHub 同步完整中文正文；`--retire-missing` 只关闭而非删除不在新树的开放对象。本地 Claude 数据仅用于 SQLite 导入验收，仓库自动门禁使用合成 fixtures。

Before flow instances are generated, the six review questions in `plans/fullstack-design` are resolved as D16–D19 and related decisions as of 2026-10-24; `05 §10` is used only as this service's client-side contract for mock integration and does not imply upstream commitment.

## Alternatives considered

Keeping old M1 并追加新阶段会继续让 scope 漂移；物理删除远端 issue 会破坏 #10/#17 等提交追溯；继续用草案表格而不流程实例无法被 scope 和状态机约束。

## Consequences

Requires a one-time迁移 GitHub milestone/issue 并关闭旧开放对象；后续新增 issue 必须提供依赖与独立验证；真实数据验收只能在本地或受控环境执行。
