# Git 工作区与推送

[English](git-workspace.en.md) | 中文

自进化 run 在 prepare 阶段按目标 ref 建立本地裸缓存，再从缓存克隆隔离工作区。代理的运维配置见 [Git 出网代理](git-proxy.md)。

## 缓存与克隆

- 缓存路径为 `HE_DATA_DIR/repos/<target>/<sha256(ref)[:16]>/`，按 target 与规范化 ref 命中；同一路径由进程内锁串行。
- tag / 分支：`git init --bare` 后执行 `git fetch --no-tags origin <ref>`，保留该 ref 的完整历史，并把解析出的 commit 写入 `refs/heads/harness-target`，供 patch、commit、ancestry 校验与本地 clone 使用。
- 完整 commit：执行 `git fetch --depth 1 --no-tags origin <sha>`，同样写入 `refs/heads/harness-target`。
- 不执行 `--mirror`。缓存 origin 与当前 `repo_url` 不一致时整体重建；已有缓存刷新失败保留完整对象，新缓存首次失败删除半成品后可重试。
- 工作区为 `HE_DATA_DIR/workspaces/<runId>`：从缓存 `git clone --no-checkout`，`remote set-url origin <repo_url>`，再创建 `evo/<date>-<runId>`。远端已有同名 run 分支时先显式 fetch 再 `switch --track`；push 前若远端 commit 不在本地对象库，先 fetch 该分支再做 `merge-base --is-ancestor`。

## 推送

- `HE_GIT_PUSH` 控制全部远端写入，默认 true；设为 false 时仍生成本地 candidate，但不推送、不评测。
- provider 自动 fork；prepare 把派生出的 push 目标写入 run 快照，eval 复用同一目标。`HE_GIT_PUSH_URL` 仍是全局兜底，target 不接受 push/eval URL 输入，前端不需要填写。push 与 eval 必须指向同一个可 fetch 的仓。
- `HE_GIT_PUSH_URL` 是可选的全局 fork / push URL 兜底。配置后 fetch 仍走 `origin`，push、候选 tag 的 `ls-remote` 与删除走独立 `push` remote；未配置时 push `origin`。
- 凭据只来自运行环境或 credential helper；HTTP(S) 地址不得内嵌凭据，仓库与数据库不保存推送凭据。
- 第三方公共仓库通常没有写权限：关闭 `HE_GIT_PUSH`，或配置可写 fork。push 失败按 `blocked(push)` 暴露，不静默记为成功。

## 托管平台与凭据

- `HE_GIT_PUSH_PROVIDER=github`（默认）或 `gitlab` 选择 `GitPushProvider` 子类；工厂在启动时实例化，未知值拒绝启动。
- `HE_GIT_PUSH_TOKEN` 是 PAT，只从 Secrets / 运行环境注入；`GIT_ASKPASS` 用 provider 的默认用户名（GitHub `x-access-token`、GitLab `oauth2`）和该 token 取值，token 不进入 URL、数据库、事件或日志。`harness` 用户没有 home，脚本用绝对路径。
- API base、网页根与 git 用户名由 provider 子类按 `repo_url` 的 host 推导（github.com / gitlab.com 用公有默认；自托管用同 host 的 `/api/v3` 或 `/api/v4`）；确有反向代理等特殊差异时在子类覆盖，不新增环境配置。
- 新增托管平台只需新增一个 `GitPushProvider` 子类与注册项；prepare / candidate / final 的状态机、失败分类与评测契约不变。

## 可观测性

`workspace_prepared` 事件 payload 记录 `ref`、`cacheHit`、`cloneSeconds`、`proxyState`（disabled / closed / open）和最多 20 条 `gitOperations`；超限时 `gitOperationsTruncated=true`。每条含 operation、viaProxy、代理前后状态、fallbackReason、durationMs、exitCode 与 targetHost。

每个 git 子进程另发一条 `git.proxy.operation` 结构化日志，带 runId、jobId 与 stage；本地缓存 clone 不产生网络流量，viaProxy=false。代理探测记为 operation=probe、runId=null。代理层失败并回退直连时 viaProxy=false，fallbackReason 为 proxy_connect / 407 / tunnel / timeout 等，其他代理层错误归为 proxy_error。日志与事件只含主机名，不含完整 URL、凭据、stderr 或代理配置。

排查时读取 `GET /api/evolution/runs/<runId>/events` 的 `workspace_prepared` payload，或按 runId 过滤 `git.proxy.operation` 日志；无需 SSH。

## 边界

- 旧 `repos/<targetId>` mirror 目录不迁移、不读取。
- 单 ref 缓存保留该 ref 的完整历史；不同 ref 各占一份目录，磁盘占用随访问过的 ref 增长。
- 工作区按保留策略清理；仓库缓存不随工作区清理，需要时人工删除。
- 代理健康探测与业务流量分开记录；探测失败不会改写某个 run 的 viaProxy 结论。
