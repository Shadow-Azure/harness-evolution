# 路线图

[English](roadmap.en.md) | 中文

## M0 脚手架（当前）

- pnpm workspace
- React + Vite 前端
- Fastify + TypeScript 后端
- 共享 contracts 包
- 健康检查打通前后端

## M1 Codex 轨迹可查看

- 扫描本机 Codex rollout JSONL
- 增量导入
- SQLite schema 与 repository
- session 列表与详情
- 按轮次展示消息、推理、工具调用、输出、错误与 token

验收：能在前端打开一个真实 Codex session，并定位到任意一条工具调用。

## M2 AI 轨迹诊断

- 规则诊断：工具失败、重复重试、未验证修改、错误未闭环等
- AI 诊断：结构化输出问题、证据与改进建议
- 诊断任务状态与历史记录
- 问题回链到轨迹

验收：前端能展示一次 session 的问题列表，并点击证据跳转到对应轨迹。

## M3 自进化闭环

- 把问题归因到 skill / prompt / 工具 / 控制流
- 生成最小改动提案
- 对照评测与采纳/回滚记录

验收：至少一条真实问题能走完“诊断 → 提案 → 对照验证 → 采纳或拒绝”的闭环。
