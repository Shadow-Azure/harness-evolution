# M24 自进化 Run 单 ref 克隆与推送

[English](m24-milestone.en.md) | 中文

```yaml flow
kind: milestone
id: m24
title: M24 自进化 Run 单 ref 克隆与推送
status: done
github:
  number: 30
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/30
```

## 目标

让自进化 run 的工作区只拉取目标 ref（分支 / tag / 完整 commit），不再对目标仓库执行全量 `--mirror`：单次冷克隆进入 10MB 级并在 60 秒上限内完成；单 ref 克隆上仍能创建 run 分支、写 patch、commit、通过 ancestry 校验并 push；run 事件与结构化日志能回答每次 ls-remote / clone / fetch / push 是否走代理、代理状态与回退原因。

## 范围

`apps/api/app/third_party_api/git/` 的 run 工作区缓存与克隆、代理可观测性、`apps/api/app/main.py` 接线、`HE_GIT_PUSH_URL` 配置、run 事件 payload、相关单测、部署与工作区文档、Agent Note 与流程文件。

## 验收

- run workspace 冷克隆不再执行 `--mirror`；tag、分支与完整 commit 都只 fetch 目标 ref。
- 缓存按 target + ref 命中与刷新；ref 变化显式 fetch；transient 失败不删除完整对象，半成品有明确清理与重试策略。
- 单 ref 克隆上可以创建 run 分支、写 patch、commit、通过 ancestry 校验并 push；推送目标与凭据策略明确，无写权限的第三方目标默认不推分支。
- run 事件记录 ref、缓存命中、耗时与代理状态（disabled / closed / open），并附有上限的逐操作 `gitOperations`；结构化日志可按 runId 过滤。
- 现有 API、契约、前端与评测契约不变。

## 非目标

不实现或调整出网代理（m18）与目标内容读取（m19）；不改 patch 生成、评测、UI 或 `preview/*` 同步契约；不改代理选择 / 熔断策略，只增加可观测性。
