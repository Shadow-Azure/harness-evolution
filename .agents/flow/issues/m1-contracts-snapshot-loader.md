# 原型契约与 Session Family 快照加载

[English](m1-contracts-snapshot-loader.en.md) | 中文

```yaml flow
kind: issue
milestone: m1
priority: P0
status: done
scope:
  - packages/contracts/**
  - apps/web/src/prototype/**
  - apps/web/package.json
  - apps/web/tsconfig.json
  - scripts/**
  - tests/**
  - plans/**
  - .agents/flow/**
  - .agents/notes/**
  - pnpm-lock.yaml
adr:
  - ../../notes/proposed/architecture/2026-10-19-session-family-prototype.md
github:
  number: 10
  url: https://github.com/Shadow-Azure/harness-evolution/issues/10
```

## 背景

Codex 的 subagent 写入独立 rollout，主任务却以 root session 为入口。原型若只读单个 JSONL，会漏掉子 agent 的执行与证据；`session_id` 又可能被子 rollout 复用，不能作为稳定主键。

## 目标

- 定义 SessionFamily、AgentNode、SkillUse、TimelineItem、Finding、AttributionTarget 与 EvidenceRef 契约。
- 建立本地快照加载器，输入 4 个 root rollout，按 parent_thread_id 递归发现全部后代。
- 以 rollout 文件身份作为主键，保留 parent、depth、agent path 与 nickname。
- 只索引元数据并懒加载单个 rollout；原始 JSONL 不进入仓库。

## 验收

- 4 个家族共 64 个 rollout、25,170 条记录、约 72.2MB，最大深度为 4。
- 家族索引能还原父子关系，且不会因复用 session_id 覆盖其他 agent。
- 加载器能按需读取单个 rollout，不在启动时解析全部 72.2MB。
- 快照包含至少 3 条跨 agent 示例问题及稳定证据锚点。
- 每条问题都能解析出 `skill | agent` 的归因目标 ID 与名称。
- 原始 JSONL 保持本地且被 gitignore；仓库 fixture 已脱敏或派生。
- 契约与加载器有自动化测试，类型检查与文档门禁通过。
