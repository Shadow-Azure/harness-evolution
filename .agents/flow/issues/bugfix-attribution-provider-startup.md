# 归因消费者随公共 AI Agent Provider 启动并继承模型

[English](bugfix-attribution-provider-startup.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-41
milestone: bugfix
depends: []
priority: P2
status: done
scope:
  - apps/api/**
  - apps/web/**
  - tests/e2e/**
  - .env.example
  - plans/**
  - .agents/**
  - AGENTS.md
  - scripts/gates.spec.mjs
  - scripts/run-e2e.mjs
  - docs/deployment*
adr: []
github:
  number: 542
  url: https://github.com/Shadow-Azure/harness-evolution/issues/542
```

## 背景

已有对象绑定可在 API 启动前写库。公共 Claude Provider 已配置时，旧的归因环境开关仍会阻止后台领取，归因模型也有独立的默认值。

## 目标

后台绑定和向导重算均随公共 Provider 的 Skill 能力启用，并使用它配置的模型。

## 设计依据

[归因预览与对象绑定](../../../plans/fullstack-design/02-features.md)

## 实现内容

由公共 Provider 声明 Skill 能力和默认模型，新任务固化 Provider 与模型，历史快照继续按既有身份回放。

## 实施步骤

1. 统一 API 启动、绑定和向导能力判断。
2. 让隔离的 Claude 调用继承共享模型配置，更新部署与界面说明。
3. 用预先写库的绑定验证重启领取与报告写入。

## 依赖与交付边界

沿用绑定队列、租约和报告表。

## 独立验证

```sh
pnpm test:api
pnpm test:web
```

## 验收标准

支持 Skill 的 Provider 可以自动处理已有绑定。仅支持分析的 Provider 可以继续使用已有报告。新快照记录公共模型，历史快照可按原模型执行。

## 门禁与 CI

运行 API、前端、流程和文档门禁。

## 非目标

生产发布与历史报告重算单独执行。
