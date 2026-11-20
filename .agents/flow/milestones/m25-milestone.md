# M25 轨迹父子关系会话级链接

[English](m25-milestone.en.md) | 中文

```yaml flow
kind: milestone
id: m25
title: M25 轨迹父子关系会话级链接
status: done
github:
  number: 35
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/35
```

## 目标

把跨 Agent 的父子关系收回到 parser 层级的会话级接口：父类定义 link 钩子，`ClaudeCodeTraceParser` 用 Claude 的 agentId 证据实现，`agent_tree` 只应用结果，不再在通用组装器里猜测 runtime 细节。

- 修复 envelope 的 `agentMeta` 缺少 `toolUseId` 时子 Agent 被 `synthetic-agent` 化、执行流堆到末尾的问题。
- 让新增 runtime 只需要在子类实现 link 钩子，不需要改公共 replay / agent_tree 的运行时分支。
- 保留无链接、歧义链接时的 `synthetic` 兜底，不伪造父子关系。

## 范围

`apps/api/app/service/acquisition/` 的 `parsers/` 与 `agent_tree`、会话级 link 接线、对应 API 单测与浏览器验收；`docs/`、`plans/`、`.agents/flow/` 与 Agent Note 的同步。

## 验收

- session 226504ab 形态的 fixture 中，3 个子 Agent 分别挂到真实的 `call_…` 触发器，结构树与 lane DAG 不再出现 `synthetic-agent`，子 lane 分别从 L1028 / L1202 / L1411 起跑。
- 父类 link 钩子默认返回空；未实现的 runtime 行为不变，`synthetic` 兜底仍覆盖缺失与歧义。
- `parser_version` 提升并重放后，存量 root 的 `agents` / `agent_events` 重建；不新增数据库列、契约字段或前端改动。
- 聚焦单测、API 测试、流程与文档门禁通过；PR 含修复前后的真实应用截图。

## 非目标

不修改评估平台的会话包投影与 `toolUseId` 透传；不改前端 lane DAG / 结构树算法；不新增数据库 schema 或共享契约字段；不把生产 Session 内容、截图或凭据提交到仓库。
