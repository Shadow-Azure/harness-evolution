# 自进化 Run 工作区改为单 ref 克隆并支持迭代推送

[English](m24-single-ref-run-workspace.en.md) | 中文

```yaml flow
kind: issue
id: m24-01
milestone: m24
depends:
  - m19-01
priority: P2
status: done
scope:
  - apps/api/**
  - deploy/**
  - docs/**
  - plans/**
  - .agents/**
  - scripts/doc-budgets.manifest.json
adr: []
github:
  number: 411
  url: https://github.com/Shadow-Azure/harness-evolution/issues/411
```

## 背景

生产自进化在 prepare 阶段由 `GitWorkspaceManager._ensure_mirror` 对目标仓库执行 `git clone --mirror`，把全部 refs 与历史下载到 `data_dir/repos/<targetId>`。目标 `obra/superpowers@v6.4.1` 的全量 mirror 实测 290MB；同一 ref 的单分支全历史只需 7.1MB（pack 3.87MiB），depth 1 为 3.3MB，sparse 子目录为 520KB。现有固定 60 秒 clone 上限在跨境链路上多次失败：run 01M7T5AA 与 01M7T729 都在 prepare 的 clone 阶段耗时 60.0 秒后失败，失败时半成品镜像被删除，重试从 0 开始。m18 的出网代理已上线，但 290MB 在 60 秒内仍不可靠。

m19 只把目标内容读取改成单 ref 浅拉取，并明确“不改 run workspace 的 mirror/push 模型”；本 issue 补上 run workspace 这一层。推送方面，`git_push` 默认 true，prepare 阶段就会把 run 分支推到 `origin`；对没有写权限的第三方公共仓库会在 push 阶段失败，因此推送目标与凭据策略也要在本次明确。

## 目标

- run workspace 冷克隆只 fetch 目标 ref（分支 / tag / 完整 commit），不执行 `--mirror`；目标仓库单次克隆进入 10MB 级并在 60 秒内完成。
- 缓存按 target + ref 命中与刷新；ref 变化显式 fetch；transient 失败保留完整对象，半成品清理与重试策略明确。
- 单 ref 克隆上可以创建 run 分支、写 patch、commit、通过 ancestry 校验并 push，行为和现有完整镜像流程一致。
- run 事件与结构化日志记录每次 git 操作（ls-remote / clone / fetch / push）是否走代理、代理状态变化、回退原因与耗时；无需 SSH 即可回答“这次 run 的哪些操作走了代理”。
- 推送目标与凭据策略明确：默认不向无写权限的第三方仓库推分支；需要推送时使用可写的 fork / 推送地址与凭据。

## 设计依据

- [04 §3 分层与目录](../../../plans/fullstack-design/04-backend-architecture.md#3-分层与目录)：`third_party_api` 隔离 git 进程，业务规则留在 service。
- [04 §9 配置项清单](../../../plans/fullstack-design/04-backend-architecture.md#9-配置项清单)：`HE_GIT_PROXY`、`HE_GIT_PUSH`、`HE_GIT_PUSH_URL` 等 git 侧配置的归属。
- [01 §2 组成与分层](../../../plans/fullstack-design/01-architecture.md#2-组成与分层)：git 读取/工作区属于出站集成边界。
- [issue #395](https://github.com/Shadow-Azure/harness-evolution/issues/395)：目标内容单 ref 浅拉取的既有实现与失败分类。
- [issue #397](https://github.com/Shadow-Azure/harness-evolution/issues/397)：git 出网代理与直连回退的边界。
- [git partial clone](https://git-scm.com/docs/partial-clone)：按需 blob 与 `--filter=blob:none` 的语义。

## 实现内容

- `apps/api/app/third_party_api/git/workspace.py`：把 `_ensure_mirror` 改为按 target + ref 的 `_ensure_ref_cache`。缓存目录为 `<repos_root>/<target>/<sha256(ref)[:16]>/`，进程内锁串行。tag / 分支在 `git init --bare` 后执行 `git fetch --no-tags origin <ref>`，保留该 ref 的完整历史，并把解析出的 commit 写入 `refs/heads/harness-target` 供本地 clone 使用；完整 commit 执行 `git fetch --depth 1 --no-tags origin <sha>`；不再执行 `--mirror`。缓存 origin 与当前 `repo_url` 不一致时整体重建；已有缓存刷新失败保留完整对象，新建失败清空半成品。
- `prepare`：workspace 仍从本地 cache `git clone --no-checkout`，再 `git switch -c evo/<date>-<runId> <base>` 并 `remote set-url origin <repo_url>`；分支/patch/commit/push 流程保持。
- 重试/恢复：新 workspace 若 `origin` 已有 run 分支，先显式 fetch `refs/heads/evo/<date>-<runId>` 到 workspace 再 `switch --track`；新 workspace 直接按 `base_commit` 建分支。`_push_run_branch` 在 `merge-base --is-ancestor <remote_commit> HEAD` 前确认远端 commit 已在本地，否则先 fetch 该分支；`push_candidate` 的 tag force-with-lease 只用 `ls-remote` 的期望 SHA，不受影响。
- 推送策略：保留 `HE_GIT_PUSH`；新增可选 `HE_GIT_PUSH_URL`（fork / push URL）。配置后所有 push、push 前的 ls-remote 与候选 tag 清理都走独立 `push` remote，fetch 仍走 `origin`；未配置时保持推 `origin`。HTTP(S) 推送地址不得内嵌凭据；凭据只从运行环境 / credential helper 获取，不入仓库或数据库。第三方无写权限目标关闭 `HE_GIT_PUSH` 或配置可写 fork。
- 对后续流程的影响：归因与聚类在 `_prepare_workspace` 之前完成，使用 Session/归因缓存与 m19 的目标内容读取，不依赖 run workspace；patch 生成只写入 `sub_dir` 下的文件，单分支全历史包含完整树；评测请求使用 candidate commit SHA 与树，SHA 不因克隆深度改变。
- run 事件：在 `workspace_prepared` 事件 payload 增加 `ref`、`cacheHit`、`cloneSeconds`、`proxyState`（`disabled` / `closed` / `open`），并附有上限（≤20）的 `gitOperations` 列表；每项含 `operation`（ls-remote / clone / fetch / push）、`viaProxy`、`proxyStateBefore` / `proxyStateAfter`、`fallbackReason`、`durationMs`、`exitCode`、`targetHost`。不记录完整 URL、凭据、stderr 或代理配置内容；超限时截断并标注 `gitOperationsTruncated`。
- 代理可观测性：每个 git 子进程发出一条结构化日志 `git.proxy.operation`（字段同上，另带 `runId` / `jobId` / `stage`；代理探测记为 `operation=probe`、`runId=null`），日志聚合可按 runId 过滤。代理层失败并直连重试时记录 `viaProxy=false` 与 `fallbackReason`（`proxy_connect` / `407` / `tunnel` / `timeout`）；健康探测与业务流量分开，避免把探测失败误判成 run 没走代理。
- 失败与清理：错误分类保持 `clone` / `reference` / `workspace` / `subdirectory` / `push` 边界，不暴露 stderr 或凭据。
- 测试：argv 断言不含 `--mirror`；覆盖 tag、分支、完整 SHA、缓存复用、ref 变化刷新、缺失 ref、失败清理；覆盖 prepare → patch → commit → ancestry → push（本地 bare 远端）、恢复场景、推送地址与事件 payload。
- 文档：新增 git 工作区说明，更新部署配置与设计文档章节，补 Agent Note，记录单 ref 克隆、缓存、推送凭据与可观测性的取舍。

## 实施步骤

1. 设计并实现 target + ref 缓存与单 ref fetch，补 argv、ref 类型、缓存命中/刷新测试。
2. 接入 prepare / workspace / push，补 commit、ancestry、push、恢复与失败清理测试。
3. 增加 run 事件的 ref、缓存、耗时、代理状态与 `gitOperations` 字段，补 API 测试。
4. 明确推送目标与凭据配置，补配置校验与文档；第三方目标默认不 push。
5. 更新 Agent Note 与文档，跑门禁并用真实仓库做一次单 ref 克隆实测。

## 依赖与交付边界

- 依赖：m19-01（目标内容单 ref 浅拉取）。
- 交付边界：只改 run workspace 的克隆/缓存/推送边界与 git 可观测性；不改 m18 的代理实现、m19 的目标内容读取、patch 生成、评测、前端或 `preview/*` 契约。
- 旧的全量 mirror 缓存目录不迁移，新布局按 target + ref 读取；推送凭据不入库。

## 独立验证

```sh
pnpm test:api
pnpm typecheck:api
pnpm verify:flow
pnpm lint:docs
```

- 单测：本地 bare 仓库的 tag、分支、完整 SHA 都能只 fetch 目标 ref；argv 不含 `--mirror`；缓存复用不重复 clone；ref 变化触发 fetch；失败分类与清理符合预期；prepare → commit → push 在本地 bare 远端通过。
- 代理可观测性测试：代理可用时记录 `viaProxy=true`；代理层失败并重试直连时记录 `viaProxy=false` 与 `fallbackReason`；代理 disabled / open 时记录对应状态；probe 与 run 流量不混淆；日志与事件不含凭据 / 完整 URL；`gitOperations` 有上限。
- 恢复场景：远端已有 run 分支 + 新 workspace，能 fetch、switch、merge-base 并快进 push；candidate tag 的 force-with-lease 不受影响；归因/聚类/patch/评测请求不因单 ref 克隆改变。
- 实测：`git clone --branch v6.4.1 --single-branch --no-tags https://github.com/obra/superpowers /tmp/sp` 的 pack 约 3.9MiB、耗时远低于 60 秒；代码路径中不再出现 run workspace 的 `--mirror`。

## 验收标准

- run workspace 冷克隆不再执行 `--mirror`；tag、分支与完整 commit 都只 fetch 目标 ref。
- 单 ref 克隆上可以创建 run 分支、写 patch、commit、通过 ancestry 校验并 push；推送目标/凭据策略明确，第三方无写权限目标默认不推分支。
- 缓存按 target + ref 命中与刷新；transient 失败不丢完整对象，半成品可重试。
- 任一 run 可从 run 事件或结构化日志回答：ls-remote / clone / fetch / push 每次是否走代理、代理状态如何变化、是否回退直连及原因（proxy_connect / 407 / tunnel / timeout 等）；无需 SSH。`gitOperations` 有上限且不含凭据。
- 现有 API、契约、前端与评测契约不变；60 秒上限内可完成目标仓库克隆。
- 重试/恢复：已有远端 run 分支时，新 workspace 能显式 fetch 该分支并继续 commit/push；不会因单 ref cache 缺 run 分支而失败。
- 归因、聚类、patch 生成与评测 commit 语义不变（仅 run workspace 的 clone 路径变化）。

## 门禁与 CI

- `pnpm test:api`、`pnpm typecheck:api`、`pnpm lint:api`、`pnpm verify:flow`、`pnpm lint:docs`、`pnpm contract:check`。
- `verify:flow --diff` 校验 PR 标题与提交的 `(#N)` 及 scope 覆盖。
- 新测试覆盖单 ref argv、缓存复用/刷新、ref 类型、push、事件字段与代理逐操作记录。

## 非目标

- 不实现或调整 Xray / VLESS 代理、Secret 与部署回退（m18）。
- 不改目标内容读取的缓存与 20 秒上限（m19）。
- 不改归因 / 聚类算法、patch 生成、评测契约、前端、预览契约或 run 的七步状态机；不改代理选择 / 熔断策略，只增加可观测性。
- 不在仓库或数据库保存推送凭据；不默认向第三方公共仓库推分支。
