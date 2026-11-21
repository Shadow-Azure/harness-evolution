# M25 多托管平台的 Git 推送提供者

[English](m26-git-push-provider.en.md) | 中文

```yaml flow
kind: milestone
id: m26
title: M26 多托管平台的 Git 推送提供者
status: planned
github:
  number: 36
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/36
```

## 目标

把自进化 run 的远端写操作从“GitHub 专用 + 全局单 URL”收敛成可替换的 Git 托管平台提供者：用工厂按 `HE_GIT_PUSH_PROVIDER` 选择 `GitHubProvider` / `GitLabProvider`，父类定义统一的推送、fork、凭据与远端查询接口，具体 URL、API、认证方式由子类实现。个人 PAT 通过 `HE_GIT_PUSH_TOKEN` 由 GitHub Secrets 下发到服务器 `.env`；目标仓的 push/eval 地址可逐 target 配置；新增托管平台时只新增一个子类，状态机、评测与业务流程不变。

## 范围

`apps/api/app/third_party_api/git/` 的 provider 抽象与 GitHub/GitLab 子类；`apps/api/app/config.py` 与 `main.py` 的工厂接线；target/run 的 push/eval 目标字段与迁移；`deploy/**` 与 `.github/workflows/deploy.yml` 的 Secret 注入；target 配置与 run 详情的状态展示；相关 API、契约、单测、文档与 Agent Note。

## 验收

- `HE_GIT_PUSH_PROVIDER` + `HE_GIT_PUSH_TOKEN` 两个配置即可在 GitHub 与 GitLab 之间切换；Deploy 将两者写入服务器 `.env`，重启后生效；换机器重新部署即可，不需要手工配置凭据。
- `GitHubProvider` / `GitLabProvider` 都实现同一父类接口；新增一个托管平台只需要新增子类与注册项，不改 GitWorkspaceManager、candidate、retry 或 eval 业务代码。
- 每个 target 可以独立配置 push/eval 仓库；prepare、candidate、final 的推送与评测取数使用同一目标，第三方只读仓可推 fork 并在 fork 上评测。
- PAT 只来自 GitHub Secrets / 服务器 `.env`（0600），不进入 URL、数据库、事件或日志；不可写/过期/权限不足时进入明确的 blocked 状态并可重试。
- 现有 GitHub 单仓行为、API、契约、前端与评测契约保持兼容；新增测试覆盖工厂、两个子类、凭据注入、target/run 快照与失败重试。

## 非目标

不实现 OAuth App / GitHub App 的交互式授权（后续独立 issue）；不实现自动 PR 回上游；不实现同一部署内按 target 选择不同 provider（先用部署级 `HE_GIT_PUSH_PROVIDER`）；不实现 GitLab CI 或其它托管平台的完整能力，只保留可扩展的 provider seam。
