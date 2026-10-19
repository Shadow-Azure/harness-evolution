# 路线图

[English](roadmap.en.md) | 中文

## M0 脚手架（已完成）

- pnpm workspace
- React + Vite 前端
- Fastify + TypeScript 后端
- 共享 contracts 包
- 健康检查打通前后端

## M1 前端体验原型（当前）

- 选择 4 个真实 Codex 主会话，递归包含全部后代 subagent
- 搜索并切换 session；展示主 agent 与全部子 agent 的执行流程图
- 本地快照适配层，不接 SQLite 与 API
- 主/子 agent 问题统一展示在同一问题面板，并归因到具体 skill 或 agent
- 按目标 skill/agent 聚合问题，模拟自进化/训练与验证指标
- 从问题到接纳/拒绝的完整演示链路

验收：能从执行流程图定位子 agent 问题，完成归因，选择目标 skill/agent，用其问题集合完成一次模拟自进化并接纳或拒绝。

## M2 Codex 轨迹服务

- 流式扫描 rollout，按 parent_thread_id 组装 session family
- 增量导入、SQLite schema 与 repository
- session、family、ingest 与 timeline API
- 前端切换为真实数据源

验收：4 个主会话家族可幂等导入，前端展示与原型一致。

## M3 AI 轨迹诊断

- 规则诊断：工具失败、重复重试、未验证修改、错误未闭环等
- 先逐 agent 分析，再由主 agent 汇总跨 agent 问题
- AI 结构化输出问题、证据与改进建议
- 诊断任务状态与历史记录
- 问题回链到轨迹

验收：主会话的一次分析覆盖全部后代 subagent，证据带 agent 路径并可跳转。

## M4 自进化闭环

- 把问题归因到 skill / prompt / 工具 / 控制流
- 按 skill 或 agent 聚合已归因问题
- 生成最小改动提案
- 对照评测与采纳/回滚记录

验收：至少一条真实问题能走完“诊断 → 提案 → 对照验证 → 采纳或拒绝”的闭环。
