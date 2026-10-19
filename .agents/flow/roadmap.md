# 路线图

[English](roadmap.en.md) | 中文

```yaml flow
kind: roadmap
milestones:
  - m1
  - m2
  - m3
  - m4
```

## M0 工程脚手架（已完成）

前后端 workspace、共享契约与健康检查已打通。

## M1 前端体验原型：Session Family 与 Agent 协作（当前）

用 4 个真实主会话家族验证最终信息架构。主 agent 与全部后代 subagent 要出现在同一张执行流程图中；根与子 agent 的问题统一出现在同一个问题面板，并可归因到某个 skill 或 agent。问题、归因与自进化数据先打桩，原型使用本地快照，不接 SQLite 与 API。详见 [m1](milestones/m1-prototype.md)。

验收：不切换 agent 也能在同一问题列表看到主、子 agent 的全部问题；从流程图或列表完成归因，选择目标 skill/agent 后聚合其问题集合，跑一次模拟自进化/训练与验证，并依据指标接纳或拒绝。

## M2 真实轨迹服务：Session Family 导入与存储

流式扫描 rollout，按 parent_thread_id 组装家族，完成幂等导入、SQLite repository 与 REST API，并用真实数据替换原型快照。详见 [m2](milestones/m2-trace-service.md)。

验收：4 个主会话家族重复导入不产生重复数据，前端展示与原型一致。

## M3 AI 轨迹诊断：跨 Agent 证据回链

规则与 AI 诊断都以 session family 为分析范围。先逐 agent 分析，再由主 agent 合并、去重并形成跨 agent 结论。详见 [m3](milestones/m3-ai-diagnosis.md)。

验收：一次主会话分析覆盖全部后代 subagent，问题可定位到 agent 路径、rollout 与事件。

## M4 自进化闭环：Skill 与 Agent 改进评测

按 skill 或 agent 聚合已归因问题，生成最小改动提案，完成对照评测与采纳/回滚记录。详见 [m4](milestones/m4-evolution-loop.md)。

验收：至少一条真实问题走完“诊断 → 提案 → 对照验证 → 采纳或拒绝”。
