# 自进化模拟与验证指标决策

[English](m1-evolution-simulation.en.md) | 中文

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
  number: 11
  url: https://github.com/Shadow-Azure/harness-evolution/issues/11
```

## 背景

归因结果需要转化为可比较的改进方案。自进化先从某个 skill 或 agent 出发，聚合归因到该目标的问题，再生成改动并调用验证平台。M1 假设平台返回指标；前端展示验证过程并让用户决定接纳或拒绝。原型只模拟接口、训练/改进与数据，不执行真实改动。

## 目标

- 定义 EvolutionTarget、EvolutionProposal、ValidationRun、MetricComparison 与 EvolutionDecision 契约。
- 先选择目标 skill 或 agent，自动聚合归因到该目标的问题集合。
- 从目标页启动一次自进化模拟，展示排队、训练/改进、验证与完成阶段。
- 展示改动说明、目标问题、baseline 与 candidate 指标以及护栏指标。
- 提供接纳与拒绝操作，并保留本地决策状态。
- 用可替换的 mock adapter 模拟验证平台接口。

## 验收

- 自进化入口必须先选择 skill 或 agent，并展示该目标的问题集合。
- 目标没有归因问题时不可启动，也不能把其他目标的问题混入本次模拟。
- 页面显示目标类型、目标名称、问题数量与每个问题的证据入口。
- 启动后能看到验证进度、候选改动与前后指标对比。
- 指标至少覆盖任务成功率、回归数、成本与时延，并明确通过阈值。
- 至少准备一个建议接纳和一个建议拒绝的模拟结果，帮助用户比较决策。
- 接纳或拒绝后状态在当前原型会话内保留，并可重置演示。
- 页面标注“模拟验证平台”，不发起外部调用、不修改代码。
