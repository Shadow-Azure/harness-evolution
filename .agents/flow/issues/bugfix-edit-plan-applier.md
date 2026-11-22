# EditPlan 契约与 edits.py 确定性应用器及 PatchBundle

[English](bugfix-edit-plan-applier.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-20
milestone: bugfix
depends:
  - bugfix-15
priority: P2
status: in-progress
scope:
  - apps/api/app/third_party_api/ai_agent/**
  - apps/api/app/third_party_api/git/workspace.py
  - apps/api/app/service/evolution/patch_source.py
  - apps/api/tests/**
  - plans/**
  - .agents/**
adr:
  - ../../notes/proposed/feature/2026-11-22-evolution-real-ai-design.md
github:
  number: 494
  url: https://github.com/Shadow-Azure/harness-evolution/issues/494
```

## 背景

设计（#487）的 patch 表示采用 SkillOpt 式编辑指令：agent 提交 EditPlan，确定性应用器执行、`git diff` 为唯一真值。本 issue 交付「计划 → 应用 → diff → bundle」的机械部分，与 provider/业务解耦、可独立测试。

## 目标

- **EditPlan 契约**（`third_party_api/ai_agent/edits.py`）：`{summary, edits: [{op: append|insert_after|replace|delete, file, target?, content?, rationale}]}`，Pydantic 模型为单一事实源。
- **确定性应用器**：按序执行纯文本操作（replace/delete 首个匹配、insert_after 锚后行边界、append 追加），逐条产出 status 报告（`applied / skipped_anchor_missing / error`），后续编辑的锚实时复查。
- **语义校验**：`file ∈ allowed_paths`；replace/delete/insert_after 的锚在文件中**存在且唯一**（多义拒绝）；`len(edits) ≤ edit_budget`（默认 8，prompt 约束 + 硬截断双重执行）；单条 content 行数上限。
- **PatchBundle**：`{files, unified_diff, note=intent.summary, intent=EditPlan, report=逐条状态}`；`PatchSource` 协议增加 `build_bundle()`（默认实现包装旧 `build()` 为单文件 bundle，旧实现零改动）；candidate 提交流程按 bundle 提交，`Harness-Patch-Hash` 幂等语义保持。

## 设计依据

- [07 §5.5.4](../../../plans/fullstack-design/07-backend-implementation.md)：EditPlan 数据契约、执行流、安全闸与「意图态 + 结果态合一」。
- [07 §5.6](../../../plans/fullstack-design/07-backend-implementation.md)：candidate 提交与 push 流程的既有接缝。

## 实现内容

- edits.py：模型、校验器、应用器、status 报告；`.harness-evolution/` 路径排除在应用 scope 外。
- patch_source.py：`build_bundle()` 默认实现与 `PATCH_SOURCE_MODES` 预留 `agent-edit` 键（真实 source 在 bugfix-21）。
- git/workspace.py：candidate 提交按 bundle 的多文件 add 与 hash。

## 实施步骤

1. EditPlan 模型 + 校验器 + 应用器单测。
2. PatchBundle 与 `build_bundle()` 默认实现。
3. workspace 多文件提交改造与既有回归。
4. 门禁：`pnpm lint:api`、`pnpm typecheck:api`、`pnpm test:api`、`pnpm verify:flow`。

## 依赖与交付边界

- 依赖：bugfix-15（包骨架）。
- 交付边界：只做机械组件与 bundle 改造；不接 agent 调用与迭代闭环（bugfix-21）。

## 独立验证

```sh
pnpm test:api -- tests/test_edit_plan_applier.py
```

- 四种 op 应用、锚缺失/多义、顺序应用互相影响、budget 截断、scope 排除全部有断言。

## 验收标准

- 同一 EditPlan + 同一 base 产出逐字节一致的 diff（确定性可重放）。
- 锚多义与越界被拒绝且错误可定位；`.harness-evolution/` 不进 diff。
- 旧 placeholder/minimal-config source 行为零改动（回归证明）。
- CI 全绿。

## 门禁与 CI

- api-static / unit-tests-api / docs-flow。
- 提交与 PR 标题带 `(#N)`。

## 非目标

- 不实现 agent-edit source 与迭代闭环（bugfix-21）。
- 不做 rejected-edit buffer。
- 不改 eval 网关。
