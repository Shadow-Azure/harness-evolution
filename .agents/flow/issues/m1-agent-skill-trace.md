# Agent 执行流程图与 Skill 使用追踪

[English](m1-agent-skill-trace.en.md) | 中文

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
  number: 8
  url: https://github.com/Shadow-Azure/harness-evolution/issues/8
```

## 背景

用户要分析主 agent，就不能漏掉它下面的所有 subagent。仅用树形列表不足以理解执行顺序，需要把主 agent 与全部子 agent 画成一张可交互执行流程图。当前 rollout 没有独立的 SkillInvocation 事件，skill 使用主要体现为读取 `SKILL.md` 及后续调用，因此需要派生事件并保留命中证据。

## 目标

- 构建主 agent 与全部子 agent 的执行流程图，节点展示 depth、agent path、nickname 与状态。
- 用有向边表达 spawn、wait、send、followup、interrupt 与返回关系。
- 节点展示 turn、工具调用、失败数与关联问题数。
- 从 `SKILL.md` 读取派生 SkillUse，记录名称、次数、路径与证据。
- 点击节点切换时间线，并可直接进入该 agent 的问题列表。

## 验收

- 20:05 家族的 4 层执行流程图可完整展开。
- 4 个 root session 的所有后代 agent 都出现在图中，不遗漏或重复。
- 从主 agent 节点可以沿协作边追踪到任一子 agent，并看清等待与返回关系。
- 点击子 agent 节点能打开其轨迹、问题数与问题列表。
- 17:32 的多类 skill 与 08:46 的重复 skill 加载都能识别。
- 选择某个 agent 后，时间线只显示其所属事件并保留返回主会话入口。
