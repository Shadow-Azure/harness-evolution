# agent-edit patch source 与迭代闭环：resume 反馈、拒绝缓冲与预算闸

[English](bugfix-agent-edit-iteration.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-21
milestone: bugfix
depends:
  - bugfix-17
  - bugfix-20
priority: P2
status: in-progress
scope:
  - apps/api/app/main.py
  - apps/api/app/service/evolution/**
  - apps/api/app/third_party_api/ai_agent/**
  - apps/api/tests/**
  - tests/e2e/**
  - .agents/**
adr:
  - ../../notes/proposed/feature/2026-11-22-evolution-real-ai-design.md
github:
  number: 488
  url: https://github.com/Shadow-Azure/harness-evolution/issues/488
```

## 背景

EditPlan 机械件（bugfix-20）与 Claude Code 子类（bugfix-17）就绪后，把 patch 生成接到真实闭环：`agent-edit` 作为第三种 patch source，edit_workspace 走「只读探索 → 提交计划 → 确定性应用 → diff → commit → push → eval」，reject 后带反馈迭代。

## 目标

- 新增 `AgentEditPatchSource`（注册 `agent-edit` 进 `PATCH_SOURCE_MODES` 与工厂，沿用「run 冻结配置优先、env 兜底」选择语义）：goal = 簇 title/description + 代表 case 证据 + 修复要求；`allowed_paths` 限定 sub_dir。
- `edit_workspace` 接线：agent 工具面 = 只读 + `Write(./.harness-evolution/edits.json5)`；EditPlan 经 submission 通道收货与语义校验，edits.py 应用，PatchBundle 落 candidate。
- **迭代闭环**：round 被 eval reject 后 `--resume` 同一会话注入反馈（delta、失败原因）+ **rejected-edit buffer**（上轮 EditPlan 摘要：已被拒绝的编辑勿重复或换皮重试）；会话 id 落 round 记录。
- 安全闸：越界 `git checkout -- .` 回滚；diff + intent + report 全量落 run events。花费防护用既有进程级手段（`--max-turns` 常量 + 超时常量），**不做 run 级预算闸**（后续有真实成本压力再加）。

## 设计依据

- [07 §5.5.4](../../../plans/fullstack-design/07-backend-implementation.md)：执行流、迭代闭环、安全闸、patch source 接入。
- [07 §5.6](../../../plans/fullstack-design/07-backend-implementation.md)：单轮 candidate → push → 评测的既有状态机接缝。

## 实现内容

- patch source 与 round 循环接线（reject → resume 注入反馈与拒绝缓冲 → 下一轮）。
- e2e：full run（fake provider）端到端产 bundle；真 CLI 冒烟开关。

## 实施步骤

1. AgentEditPatchSource + edit_workspace 接线（fake 下可测）。
2. 迭代闭环与拒绝缓冲及测试。
3. 门禁：`pnpm lint:api`、`pnpm typecheck:api`、`pnpm test:api`、`pnpm test:e2e --pattern evolution`、`pnpm verify:flow`。

## 依赖与交付边界

- 依赖：bugfix-17（真实子类）、bugfix-20（应用器与 bundle）。
- 交付边界：patch 生成与迭代闭环；不改聚类（bugfix-19）与 eval 网关本体。

## 独立验证

```sh
pnpm test:api -- tests/test_agent_edit_source.py
pnpm test:e2e --pattern evolution
```

- fake 下 full run 产出「结构化计划 → 确定性应用 → 多文件 diff → candidate」；reject 路径的 resume 反馈与拒绝缓冲有断言。

## 验收标准

- `HE_PATCH_SOURCE_MODE=agent-edit`（或 run 冻结配置）时 full run 产生真实多文件 diff 并提交 candidate；意图与 diff 一致性可审计（intent + report 落库）。
- reject 后下一轮携带反馈与拒绝缓冲；轮次上限生效。
- env 切回 placeholder 即回到今天的行为。
- CI 全绿。

## 门禁与 CI

- api-static / unit-tests-api / docs-flow / e2e。
- 提交与 PR 标题带 `(#N)`。

## 非目标

- 不做直改模式开关。
- 不做 run 级预算闸与对应配置（后续有真实成本压力再加）。
- 不改 eval 网关评分逻辑。
- 不做向量化分组。
