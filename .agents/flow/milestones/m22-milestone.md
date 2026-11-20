# M22 自进化 Run 单 ref 克隆与推送

[English](m22-milestone.en.md) | 中文

```yaml flow
kind: milestone
id: m22
title: M22 自进化 Run 单 ref 克隆与推送
status: planned
github:
  number: 30
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/30
```

## 目标

让自进化 run 的工作区只拉取目标 ref（分支 / tag / 完整 commit），而不是全部 refs：单次冷克隆从 290MB 级降到 10MB 级，60 秒上限内可完成；基于该 ref 的分支创建、patch、commit、ancestry 校验与 push 沿用现有流程；run 事件能看出本次克隆的 ref、缓存与代理状态。

## 范围

`apps/api/app/third_party_api/git/` 的工作区缓存与克隆、`apps/api/app/main.py` 接线、run 事件、相关单测、Agent Note 与流程文件；推送目标 / `HE_GIT_PUSH` 的配置说明与必要校验。

## 验收

- run workspace 冷克隆不再执行 `--mirror`；tag、分支与完整 commit 都只 fetch 目标 ref。v6.4.1 实测单分支全历史约 7.1MB / 2.5s，depth 1 约 3.3MB / 2.3s。
- 缓存按 target + ref 命中与刷新；ref 变化显式 fetch；transient 失败不删除完整对象，半成品有明确清理与重试策略。
- 单 ref 克隆上可以创建 run 分支、写 patch、commit、通过 ancestry 校验并 push；推送目标与凭据策略明确，默认不向无写权限的第三方仓库推分支。
- run 事件记录 ref、缓存命中、耗时与代理状态（disabled / closed / open），无需 SSH 即可判断是否走代理。
- 现有 API、契约、前端与评测契约不变。

## 非目标

不实现或调整出网代理（m18）与目标内容读取（m19）；不改 patch 生成、评测、UI 或 `preview/*` 同步契约。
