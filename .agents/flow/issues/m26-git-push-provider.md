# 多托管平台的 Git 推送提供者：PAT/Secrets + 工厂/子类

[English](m26-git-push-provider.en.md) | 中文

```yaml flow
kind: issue
id: m26-01
milestone: m26
depends:
  - m24-01
  - m5-09
  - m5-11
priority: P1
status: ready
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - deploy/**
  - .github/workflows/**
  - docs/**
  - plans/**
  - .agents/**
  - scripts/**
adr: []
github:
  number: 457
  url: https://github.com/Shadow-Azure/harness-evolution/issues/457
```

## 背景

生产 run `01M7VS6587C6DTQ1TBMVH5F05Z`（2026-11-20，target `skill:systematic-debugging@v6.4.1`，上游 `https://github.com/obra/superpowers`）在 prepare 阶段向第三方只读上游推送 run 分支，远端返回权限拒绝，run 以 `blocked(push)` + `run branch publication failed` 结束。随后一次人工重试把 run 从 blocked 清回 running，但 retry 任务在自身仍运行时提交后续 `evolution_prepare`，被同一 ref 的活动任务去重逻辑判为 `RUN_BUSY` 并静默吞掉；run 停在 6/7 步、0 轮次、无后续 job，形成僵尸。

这次事故暴露的不是单点：当前 `GitWorkspaceManager` 在构造时固化一个全局 `push_url`（来自 `HE_GIT_PUSH_URL`），prepare、candidate、final 的所有 push 都复用它；`HE_GIT_PUSH_URL` 留空时直接推 `origin`，对没有写权限的第三方公共仓必然 403。与此同时，评测请求固定使用 `run.repo_url` + candidate commit（`eval_poller.py:92-99`、`eval_gateway/mapper.py:45`），即使把 push 改到 fork，评测仍从上游取 commit，会把 `blocked(push)` 变成 `blocked(eval)`。target/run 没有 per-target 的 push/eval 字段，多仓场景下“一个全局 URL”无法路由；凭据也没有 `GIT_ASKPASS` / PAT 注入路径；`harness` 用户由 bootstrap 以 `--no-create-home` 创建，不能依赖 `~/.ssh` 或 `~/.git-credentials`。

用户已明确采用**个人账号 PAT**的过渡方案：GitHub Secrets 配两个值——类型（如 `HE_GIT_PUSH_PROVIDER=github`）和 PAT（`HE_GIT_PUSH_TOKEN`）；Deploy 把两者写入服务器 `.env` 后重启；实现上用**工厂 + 父类 + 子类**，父类定义统一对外接口，平台差异全部放子类；当前支持 GitHub，后续部署到其它环境（如 GitLab）时 URL、API、认证方式变化，只需新增一个子类，不改业务状态机。该诉求同时覆盖了多仓 fork、评测同源、PAT/Secrets 下发与可扩展性，适合作为一个可独立验收的纵向切片。

另有一个与本 issue 相邻但独立的缺陷：retry 任务提交后续任务时被自身 `RUN_BUSY` 拒绝。它不属于 provider 抽象，但上线前必须单独修复；本 issue 的独立验证不依赖自动 retry，只验证 push 失败进入 blocked、修复后能重试当前阶段。

## 目标

- 用 `HE_GIT_PUSH_PROVIDER` + `HE_GIT_PUSH_TOKEN` 两个核心配置切换 GitHub / GitLab：类型可选 `github`、`gitlab`，PAT 由 GitHub Secrets 注入服务器 `.env`；换机器重新部署即可，不手工配置凭据。
- 建立 `GitPushProvider` 父类（公共接口与公共 git 执行）和 `GitHubProvider` / `GitLabProvider` 子类；工厂按 `.env` 的类型实例化；新增托管平台只需新增子类 + 注册项，不改 `GitWorkspaceManager`、candidate、retry、eval 业务代码。
- prepare / candidate / final 使用同一个 per-run push 目标；评测复用同一目标；provider 自动 fork，不新增 target 字段，前端不需要填写。
- 第三方只读上游可以推到可写 fork（personal PAT 或后续机器账号），并在 fork 上评测；不再把错误推迟到 eval 阶段。
- PAT/凭据只来自 Secrets / 服务器 `.env`（0600），不进入 URL、数据库、事件、日志；push 失败、token 过期、scope 不足都进入明确的 blocked 状态并可重试。
- 保持现有 GitHub 单仓行为与 API/契约/前端/评测契约兼容；补工厂、子类、凭据、target/run 快照与失败重试测试。

## 设计依据

- [04 §3 分层与目录](../../../plans/fullstack-design/04-backend-architecture.md#3-分层与目录)：git 进程与托管平台差异留在 `third_party_api`，业务状态机留在 `service`。
- [04 §9 配置项清单](../../../plans/fullstack-design/04-backend-architecture.md#9-配置项清单)：`HE_GIT_PUSH`、`HE_GIT_PUSH_URL` 等 git 侧配置的归属与默认值。
- [07 §5.6 git 链路](../../../plans/fullstack-design/07-backend-implementation.md)：prepare / candidate / accept / final 的 push 语义与失败分类。
- [docs/git-workspace.md](../../../docs/git-workspace.md)：当前工作区、缓存、push remote 与凭据策略的现状。
- [m24-01 #411](https://github.com/Shadow-Azure/harness-evolution/issues/411)：单 ref 工作区与 push 目标/可观测性的上一阶段实现。
- [m5-09 #58](https://github.com/Shadow-Azure/harness-evolution/issues/58)：candidate commit/ref、push 重试与接纳的既有契约。
- [m5-11 #60](https://github.com/Shadow-Azure/harness-evolution/issues/60)：blocked 恢复与自动退避；本 issue 只保证 push 失败进入 blocked，不修改其调度缺陷。
- GitHub REST：[Create a fork](https://docs.github.com/en/rest/repos/forks)、[GitHub App user access token / PAT 认证](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)。
- GitLab Docs：[Fork a project](https://docs.gitlab.com/ee/api/projects.html#fork-project)、[Project access tokens / PAT](https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html)、[Git over HTTPS](https://docs.gitlab.com/ee/gitlab-basics/start-using-git.html)。

## 实现内容

### 1. 配置与工厂

- `Settings` 新增：
  - `git_push_provider: Literal["github", "gitlab"] = "github"`，来源 `HE_GIT_PUSH_PROVIDER`；未知值启动失败（`ConfigError`），不静默回退。
  - `git_push_token: SecretStr | None`，来源 `HE_GIT_PUSH_TOKEN`；为空时保留现有 credential helper 行为。
- 不新增 API base、网页根或 git 用户名配置：由 provider 子类按 `repo_url` 的 host 推导（GitHub.com `api.github.com` / `x-access-token`，GitLab.com `/api/v4` / `oauth2`；自托管用同 host 的 `/api/v3` 或 `/api/v4`）。特殊反向代理/非标准用户名在子类覆盖。
- 保留 `HE_GIT_PUSH`（总开关）与 `HE_GIT_PUSH_URL`（旧全局兜底），避免破坏现有部署。
- `GitPushProviderFactory.create(settings)`：按 registry `{"github": GitHubProvider, "gitlab": GitLabProvider}` 实例化；provider 在 composition root 构造一次，注入 `GitWorkspaceManager`，不在每次 run 里读环境。
- 工厂只负责选择实现；业务层只依赖父类接口，不 import 具体子类。

### 2. 父类与子类

```python
class GitPushProvider(ABC):
    provider_id: str

    @abstractmethod
    def remote_url(self, repo_url: str, *, fork: bool = False) -> str:
        """Return a pushable HTTPS/SSH URL with no credentials."""

    @abstractmethod
    def auth_environment(self) -> Mapping[str, str]:
        """Return GIT_ASKPASS / GIT_SSH_COMMAND / GIT_CONFIG_* without logging secrets."""

    @abstractmethod
    async def ensure_fork(self, upstream_url: str, owner: str | None = None) -> str:
        """Find or create a fork under owner and return its URL."""

    @abstractmethod
    async def open_pull_request(self, fork_url: str, upstream_url: str, branch: str, title: str) -> str | None:
        """Optional capability; return None when unsupported."""

    # Common git execution template methods: push / ls-remote / delete ref
    async def push_ref(self, workspace: Path, remote_url: str, refspec: str) -> None: ...
    async def remote_ref(self, workspace: Path, remote_url: str, ref: str) -> str | None: ...
```

- `GitHubProvider`：默认 `https://github.com` / `https://api.github.com`；`GET /user` 取登录名；`GET /repos/{owner}/{repo}` 判存在；`POST /repos/{owner}/{repo}/forks` 建 fork；HTTPS 用户名 `x-access-token`，密码 `HE_GIT_PUSH_TOKEN`；API 头 `Authorization: Bearer`。
- `GitLabProvider`：默认 `https://gitlab.com` / `https://gitlab.com/api/v4`；`GET /user` 取 username；项目路径 `owner%2Frepo`；`POST /projects/{encoded}/fork` 建 fork（可带 `namespace_path`）；HTTPS 用户名 `oauth2`，密码 PAT；API 头 `PRIVATE-TOKEN`；自托管从 `repo_url` 的 host 推导 API/网页根。
- 公共 git 执行放父类（`git push`、`git ls-remote`、删除 ref），平台差异（URL、认证、fork、PR）全部在子类；新增 `GiteaProvider` 只加子类 + registry，不改业务。
- 远端 ref 查询仍用 `git ls-remote`，不引入平台特定分支/tag 语义；candidate tag 的 force-with-lease 仍用期望 SHA。

### 3. GitWorkspaceManager 与 per-run 目标

- `GitWorkspaceManager` 不再保存单一 `_push_url`；`prepare` 按 provider 推导 fork、`HE_GIT_PUSH_URL`、`run.repo_url` 的顺序解析 push URL，并把结果写入 `run.push_repo_url`；`push_candidate` / `publish_run_branch` 接收 run 或显式 push URL，不读全局可变状态。
- 认证：`GIT_ASKPASS` 使用 provider 的默认用户名（GitHub `x-access-token`、GitLab `oauth2`）和 `HE_GIT_PUSH_TOKEN`；provider 的 `auth_environment` 注入 git 子进程；不把 token 拼进 URL；日志/事件只记 host 与 ref，不记 token。
- push 失败仍走既有 `classify_git_failure` → `blocked(push)`；不改变 retry 语义；本 issue 不修 retry 自阻塞。
- 评测：`EvalRequest.repo_url = run.push_repo_url or run.repo_url`；eval 直接复用 push 目标，保证同源。

### 4. target / run 数据与迁移

- `evolution_targets` 不新增 push/eval/凭据字段；target 仍只配置 `repoUrl/subDir/defaultRef` 等现有字段，provider 由部署级 env 选择。
- `evolution_runs` 新增 `push_repo_url`（prepare 时由 provider 派生；eval 复用）；历史行空串回退 `repo_url`。
- target API/contracts 不变；target UI 不增加输入字段，只显示 PAT 状态（已配置/缺失/过期）和“配置 PAT”说明。
- run 详情显示派生的 `pushRepoUrl` 与 blocked 原因；完整 fork 自动准备/授权状态可作为 follow-up，不增加字段。

### 5. Deploy 与 Secrets

- `production` Environment 新增：
  - `HE_GIT_PUSH_PROVIDER=github`（类型；可放 Secret 或 Variable）。
  - `HE_GIT_PUSH_TOKEN=<PAT>`（Secret，fine-grained 或 classic `public_repo`）。
- `Deploy` 的“注入部署配置”步骤把以上值按现有 base64 + `inject-config.py` 模式写入 `/opt/harness/shared/.env`（0600），并注入：
  - `GIT_ASKPASS=/opt/harness/shared/git-askpass.sh`（0755，脚本只读 env，不存 token）。
- 重启 `harness-api`；`harness` 用户无 home，凭据用绝对路径，不依赖 `~/.ssh` / `~/.git-credentials`。
- 换机器：新机跑同一 Deploy，Secrets 自动下发；真正要迁移的是 MySQL + `HE_DATA_DIR` 数据。

### 6. 安全

- token 只存在 GitHub Secrets 与服务器 0600 `.env`；不写 URL、DB、事件、日志；`SecretStr` 与统一 redaction。
- PAT 权限最小：GitHub fine-grained `Contents: R/W`、`Metadata: R`；建 fork 需 `Administration: R/W` 或 `Repository creation: R/W`（或 classic `public_repo` 兜底）；GitLab `api` / `write_repository` 按最小需要。
- 公开上游的 fork 是公开的；target 准备时明确提示；敏感内容用私有 mirror。
- 个人 PAT 是过渡：离职/轮换/审计风险由后续专用账号/GitHub App 方案收敛；本 issue 不实现 App/OAuth。

## 实施步骤

1. 增加 `HE_GIT_PUSH_PROVIDER` / `HE_GIT_PUSH_TOKEN` 两个配置与校验；实现 `GitPushProvider` 父类、`GitHubProvider`、`GitPushProviderFactory`；补工厂与配置单测。
2. 实现 `GitLabProvider`（fork、API base、oauth2 认证、URL 编码）；用本地 mock HTTP / 本地 bare remote 覆盖；补自托管 host 推导测试。
3. 重构 `GitWorkspaceManager` 的 push 路径：按 run 解析 push URL、provider 注入认证、`push_candidate` / `publish_run_branch` 去全局状态；补 prepare/candidate/final 的本地 bare remote 测试。
4. run 新增 `push_repo_url` 派生字段与迁移；prepare 写入；`eval_poller` 复用；target 不加字段；补 API/契约测试。
5. Deploy 注入两个核心配置 + `GIT_ASKPASS`；文档写明 PAT 创建、轮换、换机器与新托管平台扩展步骤。
6. target PAT 状态与 run push 目标展示；补前端测试；跑全仓门禁。
7. 新增 Agent Note，记录 provider seam、配置、凭据与扩展新平台的方法。

## 依赖与交付边界

- 依赖：m24-01（单 ref 工作区与 push 目标）、m5-09（candidate commit/ref/push）、m5-11（blocked 恢复）。
- 交付边界：只做 Git 推送 provider 抽象、PAT/Secrets 下发、run 的派生 push 目标、最小 UI 状态；不实现 OAuth/App 交互授权、自动 PR、per-target provider、target 级 push/eval 覆盖、GitLab CI 或完整 fork 自动准备。
- 保持 `HE_GIT_PUSH` / `HE_GIT_PUSH_URL` 兼容；未配置新字段时行为与今天一致。
- retry 自阻塞是独立缺陷：本 issue 不修改其调度；上线前需单独修复，否则 push 失败后仍可能停在 running。

## 独立验证

```sh
pnpm test:api
pnpm test:web
pnpm typecheck:api
pnpm typecheck:web
pnpm contract:check
pnpm verify:flow
pnpm lint:docs
pnpm test:gates
```

- 工厂：`HE_GIT_PUSH_PROVIDER=github` 得到 `GitHubProvider`，`gitlab` 得到 `GitLabProvider`，未知值启动失败；新增测试子类只加 registry，不改业务代码即可被选中。
- GitHub：本地 bare remote + mock/real fork URL；prepare/candidate/final 推送到 per-run fork；token 通过 `GIT_ASKPASS` 注入；URL/事件/日志不含 token。
- GitLab：本地 bare remote + mock API；`POST /projects/{encoded}/fork`、`PRIVATE-TOKEN`、`oauth2` 用户名、自托管 API base 均被覆盖；push/eval URL 正确。
- run：`push_repo_url` 派生快照；eval 复用；历史 run 默认回退 `repo_url`；迁移前后可读；target 没有新增字段。
- 失败：push 403/401/过期进入 `blocked(push)`，错误文案可定位；修复凭据后重试当前阶段不重跑迭代。
- 回归：不配新字段的 GitHub 单仓行为与现有测试一致；`HE_GIT_PUSH=false` 仍跳过 push 与评测。

## 验收标准

- `HE_GIT_PUSH_PROVIDER` + `HE_GIT_PUSH_TOKEN` 两个核心配置即可在 GitHub / GitLab 之间切换；Deploy 写入 `.env` 并重启后生效；换机器只重新部署。
- `GitPushProvider` 父类定义统一接口；`GitHubProvider` / `GitLabProvider` 实现平台差异；新增平台只需新增子类 + registry，不改业务状态机。
- prepare / candidate / final 使用 per-run push 目标；评测复用同一目标；第三方只读上游可推 fork 并从 fork 评测。
- PAT 不进入 URL、DB、事件、日志；缺失/过期/权限不足进入明确 blocked，可重试。
- run 迁移与 API 字段完整；target API/contracts 不变；历史 run 兼容；现有 GitHub 单仓行为不回归。
- 文档、Agent Note、测试与门禁齐全；`pnpm verify:flow` 绿。

## 门禁与 CI

- `pnpm test:api`、`pnpm test:web`、`pnpm typecheck`、`pnpm contract:check`、`pnpm verify:flow`、`pnpm lint:docs`、`pnpm test:gates`。
- `verify:flow --diff` 校验 PR 标题与提交的 `(#N)` 及 scope 覆盖。
- 新测试覆盖工厂、两个子类、认证环境、fork、per-run push/eval、run 迁移与失败重试；凭据脱敏断言。

## 非目标

- 不实现 GitHub App / OAuth App 的交互式授权（后续独立 issue）；不在本 issue 做组织审批/SSO。
- 不实现自动 PR 回上游、GitLab MR 自动创建；`open_pull_request` 只保留接口占位。
- 不实现同一部署内 per-target provider，也不做 target 级 push/eval 覆盖；provider 由部署级 `HE_GIT_PUSH_PROVIDER` 选择。
- 不实现 GitLab CI、Gitea 等完整平台能力；只验证新增子类的扩展路径。
- 不修复 retry 自阻塞、不改变 blocked 退避策略；不把凭据写入仓库/数据库/URL。
