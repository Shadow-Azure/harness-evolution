# git fetch 中断残留的 shallow.lock 会让目标内容读取与 run 准备永久失败

[English](bugfix-stale-shallow-lock.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-68
milestone: bugfix
depends:
  - m19-01
  - m24-01
priority: P2
status: ready
scope:
  - apps/api/**
  - tests/**
  - docs/**
  - .agents/**
  - plans/**
  - scripts/doc-budgets.manifest.json
adr: []
github:
  number: 649
  url: https://github.com/Shadow-Azure/harness-evolution/issues/649
```

## 背景

### 问题描述

目标内容读取（m19）与自进化 run 准备（m24）都把 shallow git 仓库当作 `HE_DATA_DIR` 下的缓存：前者是 `target-content/<repo-url hash>/<ref hash>`，后者是 `repos/<target>/<ref hash>`。两者在缓存命中后仍会执行一次 `git fetch --depth 1` 刷新 ref。如果服务在 fetch 或 shallow clone 进行期间被终止（部署重启、任务超时取消、进程崩溃、容器 kill），git 在缓存仓库里留下的 `shallow.lock` 会一直存在。

服务重启不会清理这个锁：下一次读取同一 `(repo_url, ref)` 时，`git fetch` 以 `fatal: Unable to create '.../shallow.lock': File exists.` 失败。由于缓存路径稳定、失败后目录仍被视为可复用，故障不是一次性的：该 ref 的目标定义解析、版本读取以及完整 commit 的 run 准备会持续失败，直到人工删除缓存目录或锁文件。

前端把内容读取失败映射为 `repo_unreachable`（“无法访问仓库”），把锁残留误报成网络或权限问题；workspace 侧则按可重试的 fetch 失败重复重试同一坏缓存。两个入口都没有自愈路径。

本次分析没有生产日志或现场，无法确认线上是否已经发生；以下结论来自代码路径、git 源码与本地可复现实验：故障机制成立，且一旦发生就是永久性的。

### 影响面

- `SubprocessGitContent`：分支或 tag 读取每次都会 `git fetch --depth 1`；一个残留锁会让该 `(repo_url, ref)` 缓存永久不可读，影响总览目标分析、版本解析、启动向导与目标定义冻结。
- `GitWorkspaceManager`：完整 40 位 commit ref 使用 `git fetch --depth 1`；若首次拉取在 commit 落盘前被杀，后续 prepare 会反复失败。分支或 tag 的全量 fetch 与从缓存到 workspace 的 clone 不使用 shallow 边界，不受该锁影响。
- 两个缓存都位于持久化 `HE_DATA_DIR`，没有 TTL 或启动清理；因此一次中断可以跨多次重启存活，且只影响命中的 target 或 ref，排查时容易被误判为上游仓库故障。

### 分析过程

先核对 git 的锁生命周期，再核对服务是否会在锁残留后继续复用缓存：

1. 读 git v2.50.1 源码：`fetch-pack.c` 在 `get_pack()` 之前调用 `setup_alternate_shallow()`（v0 路径约在 `fetch-pack.c:1218`，v2 路径约在 `fetch-pack.c:1563`）；`shallow.c` 的 `setup_alternate_shallow()` 用 `hold_lock_file_for_update()` 创建 `<git-dir>/shallow.lock`，直到 `commit_shallow_file()` 才把它 rename 为 `shallow`。锁覆盖整个 pack 传输与连通性检查，进程被 SIGKILL 时不会执行回滚；git 没有锁 owner 或过期检测。
2. 在本地用 git 2.50.1 复现：建立本地 remote 与 shallow 缓存，在 fetch 的 pack 阶段对进程组发 SIGKILL；`shallow.lock` 保留且内容为新 shallow 边界；下一次 `git fetch --depth 1` 返回 128 与 `Unable to create ... File exists`；已缓存 commit 的 `git cat-file -e` 与 `git show` 仍成功；删除锁后 fetch 恢复。
3. 在服务代码路径复现：用一个本地 repo 调 `SubprocessGitContent.read_file_at_commit` 冷读成功后，在同一缓存写入 `shallow.lock`；第二次读取抛 `GitContentUnavailable("repo_unreachable")`；删除锁后恢复。说明服务既不自愈，也会把本地锁误报成仓库不可达。
4. 读失败处理：`content.py` 的 `_usable()` 只看目录结构，`_fetch_ref()` 失败后直接抛 `repo_unreachable`；`workspace.py` 的 `_cache_usable()` 同样只看结构，且 `_ensure_ref_cache()` 仅在缓存本来不可用时才删除，可复用的坏缓存被保留；两者都没有清理 `*.lock`。
5. 读终止路径：`content.py` 的 `_run_process()` 在超时取消时对进程组发 SIGKILL（`content.py:394`）；`workspace.py` 的 `_terminate_process_group()` 先 SIGTERM 再 SIGKILL（`workspace.py:1756`、`1769`）；systemd 单元使用 `KillMode=mixed` 与 `TimeoutStopSec=45`（`deploy/harness-api.service:24-25`）。这些路径都可能在 shallow 锁持有期间结束 git 进程。

复现命令与关键输出（本地文件 remote，git 2.50.1）：

```sh
git init --bare cache
git -C cache remote add origin "file:///path/to/remote.git"
git -C cache fetch --depth 1 --no-tags origin refs/heads/main
# SIGKILL the process group during the second fetch's pack phase
ls cache/shallow.lock              # exists
git -C cache fetch --depth 1 --no-tags origin refs/heads/main
# exit 128: fatal: Unable to create '.../shallow.lock': File exists.
rm cache/shallow.lock
git -C cache fetch --depth 1 --no-tags origin refs/heads/main   # recovers
```

### 根因

- git 的 shallow 锁是纯磁盘锁文件，没有 owner、心跳或过期语义；进程异常退出不会回滚，后续进程也不会自动判定其失效。
- 服务把“目录结构像仓库”当作缓存可用，未把“上一次 clone 或 fetch 未完成”编码进缓存状态，也没有在 fetch 前清理本服务独占缓存中的 git 锁文件。
- 失败分类与缓存处置放大了问题：内容读取把任何 fetch 失败折叠为 `repo_unreachable`，workspace 保留可复用的坏缓存并重复重试；两者都没有“清理后重试一次或重建缓存”的自愈动作。
- 首次 shallow clone 在 `.git` 创建后就会被 `_usable()` 视为可用；被杀的 clone 因此不会被删除重建，而是继续在残缺目录上 fetch。

## 目标

- 服务被 SIGKILL 或重启后，缓存中的残留 `shallow.lock` 最多导致一次自动清理或重建，不再造成永久失败。
- `target-content` 与 `repos` 两个缓存入口共享同一套所有权、状态校验与自愈规则，不依赖人工删目录。
- 失败原因能区分“缓存锁残留或缓存不完整”和真实的仓库不可达，并在结构化日志或事件中带上 cache key 与 host，不泄露凭据。
- 覆盖部署重启、job 超时取消、进程崩溃、同 ref 并发读取与跨进程访问。

## 设计依据

- [07 §5.6 单轮执行](../../../plans/fullstack-design/07-backend-implementation.md#56-单轮执行candidate--push--提交评测fullevolutionengineadvance_one_round)：prepare、candidate 与 push 的 git 链路和失败分类边界。
- [07 §5.8.1 阻塞重试策略](../../../plans/fullstack-design/07-backend-implementation.md#581-阻塞重试策略)：现有 blocked 与 retry 语义；本 issue 只让缓存失败可自愈，不改变真实失败的重试语义。
- [04 §3 分层与目录](../../../plans/fullstack-design/04-backend-architecture.md#3-分层与目录)：git 进程、缓存与平台差异收口在 `third_party_api`，不扩散到 service。
- [docs/git-workspace.md](../../../docs/git-workspace.md)：当前缓存、克隆、推送与失败保留策略的现状说明；本 issue 需要把“可复用坏缓存”改为可自愈。
- git 锁实现：[fetch-pack.c](https://github.com/git/git/blob/v2.50.1/fetch-pack.c#L1218)、[shallow.c](https://github.com/git/git/blob/v2.50.1/shallow.c#L386)、[lockfile.c](https://github.com/git/git/blob/v2.50.1/lockfile.c)。

## 实现内容

### 1. 显式缓存所有权：跨进程文件锁

- 在两个缓存根下建立稳定的锁文件（如 `<cache_root>/.locks/<key>.lock`），用 `fcntl.flock(LOCK_EX)` 串行化同一 cache key 的 clone、fetch、清理与重建；锁文件不放在将被删除的缓存目录内，避免重建后锁 inode 失效。
- 内核在进程退出时自动释放 flock，因此不需要判定“锁是不是旧进程的”；这补上了当前 `asyncio.Lock` 只在本进程有效、重启后完全失去互斥的缺口。
- 在持有该 flock 期间，缓存内的 `shallow.lock` 及同类 git 锁文件（`index.lock`、`HEAD.lock`、`config.lock`、`packed-refs.lock`、`refs/**/*.lock`）一定不属于本服务的活跃 git 进程，可以删除后重试。

### 2. 缓存状态与自愈

- 在 clone 或 fetch 前原子写入 `incomplete` 标记（含 repo_url、ref、开始时间，fsync），成功后原子写入 `complete` 标记（含解析出的 commit）；读取时标记缺失或不匹配即视为不可复用。
- 不可复用的缓存在 flock 内删除整目录并重建。重建只针对命中的单 ref 浅缓存，成本有界，不会触碰其他 ref 的缓存。
- 旧版本留下的缓存没有标记：若不存在任何 git 锁且结构可用（`git rev-parse --git-dir` 与 origin URL 校验通过），补写 `complete` 后沿用，避免升级后全量重建；存在锁文件则按不可复用处理。
- 在超时或取消路径终止进程组后，best-effort 删除锁文件并标记 `incomplete`；即使随后进程被 SIGKILL，先落盘的 `incomplete` 标记也能让下一次读取走重建。

### 3. 失败分类与重试

- 识别 git 的锁冲突输出（`Unable to create ... shallow.lock`、`Another git process seems to be running`）；在持有 flock 的前提下清理锁并重试一次，仍失败才按 `repo_unreachable`（内容读取）或可重试 fetch 失败（workspace）上报。
- 内容读取在清理重试成功后不向调用方暴露错误；失败时新增稳定 reason（如 `cache_stale_lock`）并在日志或事件中记录 cache key、repo host、ref hash，不记录凭据或完整 stderr。
- workspace 的 `_ensure_ref_cache()` 在锁冲突或缓存不完整时删除并重建，而不是保留坏缓存重复重试；真实网络或权限失败仍保持现有 retry 与 blocked 语义。

### 4. 启动兜底与文档

- 在 `lifespan` 的 job recovery 之前扫描两个缓存根：删除不再被 flock 持有的遗留 git 锁文件，把带 `incomplete` 标记的缓存标记为待重建；启动阶段没有业务 fetch，清扫不会与活跃操作竞争。
- 更新 `docs/git-workspace.md` 的缓存失败策略：从“保留完整对象”改为“可复用缓存必须 complete，坏缓存重建”，并补中英双语。
- 新增 Agent Note 记录“缓存是派生数据、锁所有权归操作系统文件锁、失败自愈优先于保留坏缓存”的决策与取舍。

## 实施步骤

1. 在 `third_party_api/git/` 增加缓存目录与锁文件的通用小模块（跨进程 flock、原子标记、锁文件清理），先覆盖 content 与 workspace 两个调用点。
2. 改造 `SubprocessGitContent`：获取 flock、校验或重建缓存、fetch 前清理锁、失败重试一次、更新失败 reason；保持现有公开接口与超时预算。
3. 改造 `GitWorkspaceManager._ensure_ref_cache()`：同样的所有权与自愈语义；完整 commit ref 的首次拉取失败不再保留坏缓存。
4. 把超时或取消后的清理接入 `_run_process()` 与 `_terminate_process_group()`；确保清理失败不改变原始错误。
5. 增加启动清扫并接入 `main.py` 的 lifespan；保证 job recovery 前完成。
6. 补测试：SIGKILL、残留锁、半成品 clone、并发、启动清扫；更新 m19 与 m24 相关测试与失败分类断言。
7. 更新 `docs/git-workspace.md` 与 Agent Note，跑文档、流程与聚焦 API 门禁，提交注册 PR 与修复 PR。

## 依赖与交付边界

- 依赖：`m19-01`（内容读取单 ref 缓存）与 `m24-01`（run 工作区单 ref 缓存）已完成；本 issue 只修缓存生命周期与失败路径。
- 交付边界：不改变 shallow 单 ref 缓存策略、不引入全量 mirror、不改变 run 状态机与评测契约；不新增环境变量或部署依赖。
- 单实例部署是当前前提；flock 仍应保证同机多进程安全，但不承诺多主机共享同一 `HE_DATA_DIR` 的分布式锁。
- 旧缓存升级必须无感：无锁且结构可用的缓存直接沿用，不强制全量重建。

## 独立验证

```sh
pnpm test:api -- tests/bugfix-68-stale-shallow-lock
pnpm test:api -- tests/m19-01-git-single-ref
pnpm test:api -- tests/m24-01-git-single-ref-workspace
pnpm verify:docs
pnpm verify:flow
```

- 残留锁：预置 `shallow.lock` 后读取同一 ref，自动清理并成功返回；断言没有向调用方暴露 `repo_unreachable`。
- SIGKILL：在本地大 pack 的 shallow fetch 期间杀掉进程组，新进程用同一缓存读取，第一次触发重建后成功；进程退出后锁文件不残留。
- 半成品 clone：在 `.git` 创建后杀掉 clone，下一次读取删除并重建，不在残缺目录上 fetch。
- 并发：两个进程或两个 manager 同时读同一 cache key，flock 串行化，只有一个 fetch，且都返回同一 commit。
- 启动清扫：预置遗留锁与 `incomplete` 缓存，启动后对应 target 的读取或准备成功；结构完好的旧缓存不被删除。
- 真实不可达：断网或错误 URL 仍按 `repo_unreachable` 或可重试 fetch 失败上报，不被误判为锁冲突。

## 验收标准

- 在 shallow fetch 被 SIGKILL 或部署重启中断后，不重启、不人工删目录，下一次读取或 prepare 能自动恢复（允许一次重建）。
- 同一 `(repo_url, ref)` 的并发读取不会因为清理或重建互相踩踏；缓存始终由 flock 串行化。
- 失败原因能区分锁残留或缓存不完整与真实仓库不可达，日志或事件可定位 cache key、host、ref，且不含凭据。
- 旧版本缓存升级后行为不变；无锁且结构可用的缓存不被重建。
- 测试覆盖内容读取与 run 工作区两条路径，现有 m19 与 m24 测试不回归。

## 门禁与 CI

- `pnpm test:api`（新增 bugfix-68 测试与 m19、m24 回归）、`pnpm verify:docs`（中英配对与链接）、`pnpm verify:flow`（本 issue 的三件套与状态）。
- 涉及 `third_party_api/git` 的失败分类与日志改动需同步单测；不新增契约字段时不引入契约变更。
- CI 必须执行新增测试；真实 SIGKILL 用例只使用本地文件 remote 与临时目录，不访问外网、不依赖生产数据。

## 非目标

- 不改为非 shallow 的全量缓存，也不引入 mirror 或服务端代理来规避锁。
- 不实现多主机共享 `HE_DATA_DIR` 的分布式锁或缓存一致性。
- 不改变 run 状态机、blocked 与 retry 的产品语义和评测契约；只让同一阶段的缓存失败可自愈。
- 不清理 `workspaces/` 下与本次锁无关的历史工作区，也不改缓存容量或 TTL 策略。
