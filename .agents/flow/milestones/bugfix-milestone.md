# Bugfix 问题修复

[English](bugfix-milestone.en.md) | 中文

```yaml flow
kind: milestone
id: bugfix
title: Bugfix 问题修复
status: done
github:
  number: 34
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/34
```

## 目标

统一承接后续所有 bugfix issue，不再为单个问题新增 milestone；一个 issue 只描述一个可独立验收的问题，修复面以该 issue 的 scope 为准。

## 范围

后续 bugfix issue 及其 `apps/web/**`、`apps/api/**`、`tests/**`、`scripts/**`、`plans/**`、`.agents/**` 等改动；具体每个 issue 的允许修改面仍由该 issue 的 `scope` 收口。

## 验收

每个 bugfix issue 的实现、验证与截图证据按该 issue 的验收标准交付；最终验收由提出人确认整条流程暂时没有发现问题，确认前不关闭 issue。

## 非目标

不按单个问题新开 milestone；不把无关重构、设计改版或跨模块重排塞进 bugfix issue；不把生产 Session 内容、截图或凭据写入仓库。
