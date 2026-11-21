# Agent Note: 常驻 Bugfix milestone 不随 issue 全 done 关闭

Status: implemented

[English](2026-11-20-standing-bugfix-milestone.en.md) | 中文

## Problem

Bugfix 虚拟 milestone 的设计目标是一次性承接后续所有 bugfix issue，不为单个问题新开 milestone。但 `verify:flow` 的机械规则是「milestone done ⟺ 其 issue 全 done」，`flow:sync` 又把本地 `done` 映射为关闭远端 milestone。于是一个 bugfix 完成、本地流程树里该 milestone 的 issue 全部 done 后，闭环操作会顺手关闭远端 milestone；而此时远端可能已有新的 bugfix issue（本次就有 #434/#435 尚未进入本地流程树），关闭常驻桶既不准确也会影响后续登记。

本次闭环 #423 时，milestone #34 被 `flow:sync` 短暂关闭，提出人明确要求「bugfix milestone 不要关闭」，随后重开。问题不在一次操作，而在流程模型缺少「常驻」语义。

## Decision

- milestone 的 yaml flow 围栏新增可选 `standing: true`；`bugfix-milestone` 声明为常驻桶，status 保持 `active`。
- `verify:flow` 对 `standing: true` 的 milestone 跳过 status ↔ 「issue 全 done」的等价校验：它可以在 issue 全 done 时仍为 active，也可以在有未 done issue 时为 active；`flow:sync` 按 status 把它同步为 open。
- 退役常驻 milestone 必须由 roadmap 显式决策：把 status 改为 `done` 再 `flow:sync`，不靠 issue 完成度自动推导。
- 规则落在 `.agents/flow/README.md` 与英文侧；`scripts/gates.spec.mjs` 增加常驻 milestone 通过、非布尔 `standing` 报错的用例。
- 常驻桶固定在 roadmap 序列末尾，新增 milestone 写在它之前；其长期 open 的验收 issue 不能通过「跨 milestone 同 priority 串行」阻塞后续 milestone。
- issue #423 由提出人重新打开，保持 ready 等待验收；Bugfix milestone 保持 active/open，并继续承接后续 bugfix issue。

## Alternatives considered

- **保持自动关闭、每次新 bugfix 再重开 milestone**：会产生关闭/重开的抖动，且新 issue 未进本地流程树时远端状态与本地不一致；本次已经实际触发。拒绝。
- **在代码里写死 `id === "bugfix"` 的例外**：规则会藏在实现里，无法解释为什么只有 bugfix 特殊；任何其他常驻桶都要再改代码。显式 `standing` 字段可读、可测试、可复用。拒绝。
- **把远端「是否有 open issue」纳入离线 gate**：离线 gate 不应依赖 GitHub 网络与实时状态，且 CI token 可见性不同；常驻语义应由本地声明表达。拒绝。

## Consequences

- 常驻 milestone 的 status 是人工/roadmap 决策，不再由 issue 完成度自动推导；忘记退役时 gate 不会报红，需要 roadmap 评审兜底。
- `standing` 只允许布尔值，未声明的 milestone 保持原有等价规则；已有 milestone 行为不变。
- 远程 milestone 由 `flow:sync` 按 status 打开/关闭；本次 #34 已重开，后续闭环 PR 会保持 open。
- bugfix 桶位于 M27 之后；后续新增 milestone 必须插在常驻桶之前，否则同档阻塞会重新出现。
- 流程文档、门禁自测试与本 Note 同 PR 更新；若未来需要更多常驻桶，只需加 `standing: true`，不改代码。
