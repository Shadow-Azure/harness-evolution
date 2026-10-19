# 问题归因解释与推断路径

[English](m1-attribution-explainability.en.md) | 中文

```yaml flow
kind: issue
milestone: m1
priority: P0
status: backlog
scope:
  - apps/web/src/**
  - packages/contracts/**
adr:
  - ../../notes/proposed/architecture/2026-10-19-session-family-prototype.md
github:
  number: 9
  url: https://github.com/Shadow-Azure/harness-evolution/issues/9
```

## 背景

只列出问题不足以支持自进化。用户需要看懂问题是什么、造成什么影响、为什么推断出这个原因，以及它应归因到哪个 skill 或 agent。M1 先用人工核对的归因快照验证表达方式，问题收集方式后续再讨论。

## 目标

- 定义 FindingAttribution、AttributionTarget、CausalStep、InferenceStep 与 EvidenceRef 契约。
- 从问题面板进入归因详情，先给出通俗摘要，再展示因果链与推断过程。
- 每个推断步骤必须回链证据，并区分已证实、推测与未知。
- 展示被排除的候选原因，让用户理解为什么没有采纳其他解释。
- 支持跨 agent 归因，标明主 agent 与相关 subagent 各自贡献的证据。
- 每条归因明确指向一个 skill 或 agent，并解释为什么选择这个目标。

## 验收

- 每条示例问题都能用一段非技术语言说明“发生了什么、影响是什么”。
- 每条问题都显示归因目标类型、目标名称、目标 ID 与选择理由。
- 因果链至少包含触发条件、直接原因与最终影响三个层次。
- 推断步骤逐步引用 rollout、agent、turn 或工具调用证据，点击可定位。
- 页面明确展示置信度、未证实部分和被排除的候选原因。
- 跨 agent 问题能展开到相关子 agent，而不是只给主线程结论。
- 页面标注“示例归因”，不冒充实时模型推断。
