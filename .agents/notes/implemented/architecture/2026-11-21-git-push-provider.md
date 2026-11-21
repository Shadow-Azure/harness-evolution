# Agent Note: 多托管平台的 Git 推送提供者

Status: implemented

[English](2026-11-21-git-push-provider.en.md) | 中文

## Problem

自进化 run 的远端写操作目前由一个 `GitWorkspaceManager` 实例和一个全局 `HE_GIT_PUSH_URL` 承担：prepare、candidate、final 的 push 都复用同一个地址，留空时推 `repo_url` 的 origin。对没有写权限的第三方公共上游，这必然以 403 进入 `blocked(push)`；对多个不同上游仓，一个全局 URL 也无法路由。target/run 没有 per-target 的 push/eval 字段，评测又固定使用 `run.repo_url`，所以即使把 push 改到 fork，评测仍会从上游取 candidate commit，把失败推迟到 eval。凭据只有服务器 credential helper 一条路；`harness` 用户由 bootstrap 以 `--no-create-home` 创建，不能依赖 `~/.ssh` 或 `~/.git-credentials`。

生产 run `01M7VS6587C6DTQ1TBMVH5F05Z` 就是这条链路的实例：prepare 向只读上游 `obra/superpowers` 推 run 分支被拒，run 进入 blocked；随后的人工重试又因 retry 任务被自身 `RUN_BUSY` 拒绝而停在 6/7。这个 Note 只处理 provider 与凭据/目标抽象；retry 自阻塞是独立缺陷。

用户要求采用个人账号 PAT 的过渡方案，并在 GitHub Secrets 中只配两个值：类型（`HE_GIT_PUSH_PROVIDER`）和 PAT（`HE_GIT_PUSH_TOKEN`）。实现必须用工厂 + 父类 + 子类，新增托管平台（如 GitLab）时只新增子类，不改业务状态机。

## Decision

在 `third_party_api/git/` 增加 `GitPushProvider` 父类、`GitHubProvider` / `GitLabProvider` 子类与 `GitPushProviderFactory`。父类定义 `remote_url`、`auth_environment`、`ensure_fork`、`open_pull_request` 以及公共 `push_ref` / `remote_ref`；子类只实现托管平台 URL、API、fork 与认证差异。工厂按 `HE_GIT_PUSH_PROVIDER`（`github` 默认，`gitlab` 可选）实例化，未知值启动失败；provider 在 composition root 构造一次并注入 `GitWorkspaceManager`，同时把 `auth_environment()` 合并进代理感知的 git 子进程环境。

`run.push_repo_url` 是 prepare 写下的派生目标：已有快照优先复用，否则 provider 自动 fork；未配置 token 时回退 `HE_GIT_PUSH_URL`，两者都为空时保持原有推 `origin` 行为。run 详情经 `workspace.pushRepoUrl` 暴露该目标；target API/契约与表单不新增字段。

PAT 通过 `HE_GIT_PUSH_TOKEN` 从 GitHub Secrets 注入服务器 `.env`（0600），Deploy 同时注入绝对路径的 `GIT_ASKPASS` 脚本；git 子进程从环境拿凭据，token 不进入 URL、数据库、事件或日志。API base、网页根与 git 用户名由子类按 `repo_url` host 推导（GitHub：`api.github.com` / `x-access-token`；GitLab：`/api/v4` / `oauth2`；自托管用同 host 的 `/api/v3` 或 `/api/v4`），特殊反向代理/非标准用户名在子类覆盖，不新增环境配置。

不新增 target 的 push/eval/凭据字段：provider 自动 fork，prepare 把派生的 push 目标写入 `run.push_repo_url`，回退 `HE_GIT_PUSH_URL` 与 `repo_url`；eval 复用同一目标。prepare、candidate、final 使用 per-run push 目标，保证 push 与 eval 同源。`HE_GIT_PUSH` 与 `HE_GIT_PUSH_URL` 保持兼容；同一次部署只选择一个 provider，per-target provider、OAuth/App、自动 PR 与 GitLab CI 不在本决策内。

## Alternatives considered

- **一个全局收集仓**：push 能成功，但评测从 target 的 `repoUrl` 取 commit，收集仓里的 commit 不在目标仓；不同上游的历史、tag、权限与审计也会混在一起。否决。
- **每个仓一套部署**：今天就能用，但 N 套 API/DB/升级与割裂的跨仓视图，不适合作为长期方案。仅作为临时运维手段。
- **OAuth App / GitHub App 交互授权**：比 PAT 更正式，但需要同意页、refresh token、组织审批与更多代码；已在授权调研中记录，作为后续独立切片，不与 provider 抽象捆绑。
- **每个 target 自带 provider 类型**：同一部署内支持多托管平台，但会扩大配置与测试面；当前需求是“换部署时换平台”，部署级 `HE_GIT_PUSH_PROVIDER` 足够，per-target 留待后续。
- **继续硬编码 GitHub**：无法满足 GitLab 与新增平台扩展，且把全局 URL 的问题留在原地。

## Consequences

- 新增平台只需一个子类 + 注册项；prepare/candidate/final 状态机与评测契约不变。
- target/run 需要迁移新字段；旧 run/未配置字段回退现有行为，保持兼容。
- Deploy 需要新增 `HE_GIT_PUSH_PROVIDER` 与 `HE_GIT_PUSH_TOKEN`，以及 `GIT_ASKPASS` 注入；换机器重新部署即可，不手工配凭据。
- PAT 状态不在 target 页面暴露：target 契约保持不变，凭据属于部署级配置；run 详情只显示派生后的 push 目标。
- PAT 仍是个人长期凭据，存在离职/轮换/审计风险；本 Note 只把它作为过渡，专用账号/App 由后续切片收敛。
- 公开上游的 fork 仍是公开的；敏感内容需要私有 mirror。
- GitLab 与 GitHub 的 fork/API/用户名字段不同，必须由子类测试覆盖；provider 契约要保持最小，避免把平台字段泄漏到业务层。
- retry 自阻塞不在本决策内；上线前需单独修复，否则 push 失败后仍可能停在 running。
