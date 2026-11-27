# Agent Note: Git 缓存以文件锁与生命周期标记自愈

Status: implemented

[English](2026-11-27-git-cache-self-healing.en.md) | 中文

## Problem

目标内容读取（`target-content`）与 run 准备（`repos`）都把单 ref shallow 仓库当作 `HE_DATA_DIR` 下的持久缓存，并在命中后执行 `git fetch` 刷新。git 的 `shallow.lock` 是纯磁盘锁：fetch 的 pack 传输期间持有，进程被 SIGKILL 或部署重启终止时不会回滚，也没有 owner 或过期语义。服务原先只按目录结构判断缓存可用，且进程内 `asyncio.Lock` 在重启后完全失去互斥，因此一次中断会让同一 `(repo_url, ref)` 永久失败，直到人工删除锁或缓存目录；内容读取还把该本地故障误报成 `repo_unreachable`，workspace 则反复重试同一坏缓存。

## Decision

- 新增 `third_party_api/git/cache.py`，让两个缓存入口共用所有权与生命周期规则，而不是各写一套清理逻辑。
- 每个 cache key 在缓存根的 `.locks/` 下用 `fcntl.flock(LOCK_EX)` 串行 clone、fetch、清理与重建；锁文件放在将被删除的缓存目录之外。进程死亡时内核自动释放锁，所以不需要判断锁是否属于旧进程。
- 缓存目录旁放 `<ref-key>.state.json`：clone 或 fetch 前原子写入 `incomplete`（含 repo_url、ref、开始时间并 fsync），成功后写入 `complete`（含解析出的 commit）。标记放在目录外，因为 `git clone` 要求目标目录为空。
- 命中缓存后先在 `flock` 内清理 `shallow.lock`、`index.lock`、`HEAD.lock`、`config.lock`、`packed-refs.lock` 与 `refs/**/*.lock`，再执行 fetch；git 报锁冲突时清理并重试一次，仍失败才以新增的 `cache_stale_lock`（内容读取）或可重试 fetch 失败（workspace）上报，并写带 cacheKey、repoHost、refHash 的结构化日志。
- `incomplete`、结构损坏、origin 不符或带 git 锁的缓存整体删除并重建；刷新失败时完整缓存保留并恢复 `complete`；SIGKILL 留下的 `incomplete` 在下次读取时触发一次性重建。
- 旧版本无标记的缓存：无 git 锁且结构可用时补写 `complete` 沿用，避免升级后全量重建；带锁的旧缓存按不可复用处理。
- API 启动在 job recovery 之前清扫两个缓存根，删除 `incomplete` 缓存与带锁旧缓存，清理不再被 `flock` 持有的遗留锁；结构完好的旧缓存不动。

## Alternatives considered

- **每次 fetch 前无条件删除 git 锁、不加跨进程锁**：另一个进程正在 fetch 时会把活跃锁删掉，反而制造并发写坏缓存。拒绝。
- **把跨进程锁文件放在缓存目录内**：重建会删除整个目录，等待中的进程会锁住失效 inode，新进程又能创建新锁并发进入。拒绝。
- **任何 fetch 失败都删除缓存重建**：一次网络抖动就会丢掉完整对象并放大重建成本，违背“真实失败保持现有 retry 语义”。拒绝。
- **只依赖进程内 `asyncio.Lock`**：重启与多进程不再互斥，正是本问题的一半。拒绝。
- **把状态标记写进缓存目录**：`git clone` 拒绝非空目标目录，首次 clone 会失败。拒绝。
- **启动时无条件删除所有无标记旧缓存**：升级会触发全量重建，违背无感升级要求。拒绝。

## Consequences

- 每次缓存操作多两次原子文件写入与一次 `flock`；同一 cache key 的读取本来就串行，阻塞等待的代价有界。
- 缓存是否可复用由标记与 git 锁共同决定，不再只看目录结构；损坏缓存的重建成本限于单个 ref。
- 内容读取新增稳定的 `cache_stale_lock` reason，运行日志新增 `git.cache.stale_lock` 与 `git.cache.sweep` 事件。
- 仍只保证单机多进程；不承诺多主机共享 `HE_DATA_DIR` 的分布式锁或缓存一致性。
- 测试覆盖残留锁、半成品缓存、旧缓存、并发、启动清扫与 SIGKILL 释放 flock；m19 与 m24 的既有缓存语义保持通过。
