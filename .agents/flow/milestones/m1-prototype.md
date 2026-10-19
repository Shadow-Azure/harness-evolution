# M1 前端体验原型：Session Family 与 Agent 协作

[English](m1-prototype.en.md) | 中文

```yaml flow
kind: milestone
id: m1
title: M1 前端体验原型：Session Family 与 Agent 协作
status: active
github:
  number: 5
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/5
```

## 目标

用真实复杂轨迹验证最终信息架构，先获得可评审的前端体验，再投入数据库与模型调用。

## 范围

- 4 个主会话家族：20:05:12、17:32:52、08:46:41、12:34:14
- 搜索并切换 session，从家族摘要进入完整执行流
- 主 agent 与全部子 agent 的执行流程图，保留父子关系、agent 路径与状态
- turn 时间线、skill 使用和打桩的家族级问题面板
- 根与子 agent 问题统一展示在同一列表，并归因到具体 skill 或 agent
- 问题归因页：问题、影响、原因、推断步骤、证据与归因目标
- 自进化模拟页：选择目标 skill/agent、聚合问题、模拟训练/改进与验证
- 本地快照适配层；不接 SQLite、不接正式 API、不调用模型

## 验收

- 64 个 rollout 可索引和懒加载，记录数 25,170，原始载荷约 72.2MB
- 能搜索、筛选并切换 4 个 session，刷新后恢复当前选择
- 执行流程图覆盖最深层级为 4 的全部后代 agent，并可切换到任一节点
- 同一 skill 的重复加载可见，并回链到对应工具调用
- 不切换 agent 也能在同一问题列表看到主、子 agent 的全部问题
- 每条问题标注来源 agent，并可从流程图或列表打开证据
- 每条问题都归因到某个 skill 或 agent，并说明目标、证据与推断过程
- 自进化先选择目标 skill/agent，自动汇总其问题，再模拟训练/改进与验证
- 能依据前后指标接纳或拒绝改动，并保留决策状态
- 长 turn、大工具输出、图片与 MCP 结果不会阻塞首屏
- 原始 JSONL 不进入仓库，仓库只保留脱敏或派生 fixture

## 非目标

- SQLite、增量导入、REST API
- 实时模型分析
- 真实验证平台、真实代码改动、自动合并与模型权重训练
