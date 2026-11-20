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
- `HE_GIT_PUSH_URL` 可选，指向可写 fork / push URL。配置后 fetch 仍走 `origin`，push、候选 tag 的 `ls-remote` 与删除走独立 `push` remote；未配置时 push `origin`。
- 凭据只来自运行环境或 credential helper；HTTP(S) 地址不得内嵌凭据，仓库与数据库不保存推送凭据。
- 第三方公共仓库通常没有写权限：关闭 `HE_GIT_PUSH`，或配置可写 fork。push 失败按 `blocked(push)` 暴露，不静默记为成功。

## 可观测性

`workspace_prepared` 事件 payload 记录 `ref`、`cacheHit`、`cloneSeconds`、`proxyState`（disabled / closed / open）和最多 20 条 `gitOperations`；超限时 `gitOperationsTruncated=true`。每条含 operation、viaProxy、代理前后状态、fallbackReason、durationMs、exitCode 与 targetHost。

每个 git 子进程另发一条 `git.proxy.operation` 结构化日志，带 runId、jobId 与 stage；工作区从本地缓存 clone 不产生网络流量，viaProxy=false，真正的远端交互是 fetch / ls-remote / push。代理探测记为 operation=probe、runId=null。代理层失败并回退直连时 viaProxy=false，fallbackReason 为 proxy_connect / 407 / tunnel / timeout 等，其他代理层错误归为 proxy_error。日志与事件只含主机名，不含完整 URL、凭据、stderr 或代理配置。

排查时读取 `GET /api/evolution/runs/<runId>/events` 的 `workspace_prepared` payload，或按 runId 过滤 `git.proxy.operation` 日志；无需 SSH。

## 边界

- 旧 `repos/<targetId>` mirror 目录不迁移、不读取。
- 单 ref 缓存保留该 ref 的完整历史；不同 ref 各占一份目录，磁盘占用随访问过的 ref 增长。
- 工作区按保留策略清理；仓库缓存不随工作区清理，需要时人工删除。
- 代理健康探测与业务流量分开记录；探测失败不会改写某个 run 的 viaProxy 结论。
