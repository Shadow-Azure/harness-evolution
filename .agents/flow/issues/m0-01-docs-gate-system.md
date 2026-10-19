# 文档、检视与流程门禁体系

[English](m0-01-docs-gate-system.en.md) | 中文

```yaml flow
kind: issue
milestone: m0
priority: P0
status: done
scope:
  - AGENTS.md
  - README.*
  - docs/**
  - .agents/**
  - plans/**
  - scripts/**
  - .github/**
  - .gitattributes
  - package.json
  - tsconfig.json
  - apps/**
  - packages/**
adr:
  - ../../notes/implemented/process/2026-10-19-docs-gate-system.md
github:
  number: 1
  url: https://github.com/Shadow-Azure/harness-evolution/issues/1
```

## 背景

仓库只有前后端脚手架，文档、流程与检视没有机械约束；阶段目标与任务边界容易散落在对话里。

## 目标

- 建立 docs 分层、双语三件套、Agent Notes 与 postmortem 结构。
- 建立 roadmap → milestone → issue 流程树、状态机与 GitHub 同步工具。
- 建立 doc-quick / doc-sync 门禁、CI 接线与本地钩子。
- 移植 PR 检视与 Computer Use 技能。

## 验收

- `pnpm lint:docs`、`pnpm verify:docs` 与 `pnpm verify:flow` 全绿。
- 五套 skill 位于 `.agents/skills/`，检视规范位于 `docs/review.md`。
- CI 静态 lane 运行文档门禁，PR lane 运行 flow diff 校验。
