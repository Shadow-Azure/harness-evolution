# 对象绑定归因 Skill、后台分析与报告缓存

[English](m12-bound-skill-attribution.en.md) | 中文

```yaml flow
kind: issue
id: m12-27
milestone: m12
depends:
  - m12-26
priority: P0
status: done
scope:
  - apps/**
  - packages/contracts/**
  - plans/**
  - .agents/**
  - docs/**
  - tests/**
  - scripts/**
  - deploy/**
  - .github/workflows/deploy.yml
adr:
  - ../../notes/implemented/feature/2026-11-18-attribution-skill-package-admin.md
github:
  number: 417
  url: https://github.com/Shadow-Azure/harness-evolution/issues/417
```

## 背景

工作空间包和运行归因已有独立配置路径。

## 目标

每对象绑定一个包，后台产出的报告可以直接用于自进化。

## 设计依据

[自进化设计](../../../plans/fullstack-design/02-features.md#对象绑定归因)

## 实现内容

持久化绑定、后台任务、报告 Skill 和逐 case 缓存统计。

## 实施步骤

实现后台归因、运行级选择、资源详情和原型。

## 依赖与交付边界

复用 m12-26 本地执行器及统一报告脚本。

## 独立验证

运行 pnpm test:api 与 pnpm test，使用同一 Badcase 的两份历史报告验证。

## 验收标准

每个对象版本按 Badcase 仅统计最新报告，重算保持对象绑定。

## 门禁与 CI

API、Web 测试、生成契约、类型检查及原型前后截图。

## 非目标

部署模型、修改下游聚类算法。
