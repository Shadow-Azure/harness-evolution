# Agent Note: 自进化 Run 工作区单 ref 克隆与逐操作可观测性

Status: implemented

[English](2026-11-20-single-ref-run-workspace.en.md) | 中文

## Problem

自进化 prepare 的工作区缓存此前对目标仓库执行 `git clone --mirror`。目标 `obra/superpowers@v6.4.1` 的全量 mirror 实测 290MB，跨境链路在固定 60 秒上限内多次失败；失败时半成品镜像被删除，重试从零开始。同一个 ref 的单分支全历史约 7.1MB，只读一个 ref 却下载全部 refs 是失败窗口的根源。另一个问题是代理状态只在进程内熔断器里，无法回答某次 run 的哪一步走了代理、何时回退直连。

## Decision

run workspace 的缓存改为按 target + ref 的裸仓库：`data/repos/<target>/<sha256(ref)[:16]>/`，进程内锁串行同一路径。tag / 分支用 `git fetch --no-tags origin <ref>` 保留该 ref 的完整历史，并把解析出的 commit 写到 clone 可见的 `refs/heads/harness-target`；完整 commit 用 `--depth 1` 后写同一个本地 ref，因为本地 clone 只复制被 advertise 的 refs。工作区仍从缓存 `git clone --no-checkout` 后建 `evo/<date>-<runId>`，fetch 继续走 `origin`。缓存 origin 与当前 `repo_url` 不一致时整体重建；已有缓存刷新失败保留完整对象，新缓存首次失败删除半成品。

单 ref 缓存不含 run 分支。新工作区在 `origin` 已有 run 分支时先显式 fetch 该分支再 `switch --track`；push 前如果远端 commit 不在本地对象库，先 fetch 分支再做 `merge-base --is-ancestor`。这样恢复不依赖缓存里恰好有 run 分支，也不会把「对象缺失」误判成非快进。

推送保留 `HE_GIT_PUSH` 总开关，新增可选 `HE_GIT_PUSH_URL`。配置后 fetch 仍走 `origin`，push、候选 tag 的 `ls-remote` 与删除走独立 `push` remote；未配置时保持推 `origin`。HTTP(S) 地址拒绝内嵌凭据，凭据只来自运行环境或 credential helper；第三方只读目标关闭推送或配置可写 fork，push 失败按 `blocked(push)` 暴露。

可观测性分两层。进程层给每个 git 子进程发一条 `git.proxy.operation` 结构化日志，字段含 operation、viaProxy、代理前后状态、fallbackReason、durationMs、exitCode、targetHost，以及 runId / jobId / stage；代理探测记为 operation=probe、runId=null，避免健康探测与业务流量混淆。run 层用 contextvar 把 prepare 期间的网络操作收进一个有上限（20 条）的列表，投影到 `workspace_prepared` 事件的 `ref`、`cacheHit`、`cloneSeconds`、`proxyState` 与 `gitOperations`；超限用 `gitOperationsTruncated` 标注。记录只含主机名，不含完整 URL、凭据、stderr 或代理配置。

## Alternatives considered

- **保留 mirror，只把 clone 改成 shallow。** 否决：mirror 的语义就是全部 refs，shallow mirror 仍要处理所有 ref 的浅历史，无法把「只读一个 ref」落实到缓存键。
- **每次 run 直接 `git clone --single-branch` 到工作区，不做缓存。** 否决：同一 target + ref 的重复 run 会反复下载同一份 7MB 历史，而缓存命中与显式刷新正是本 issue 的验收项。
- **复用 m19 的目标内容缓存。** 否决：m19 的缓存带 `--filter=blob:none` 且目标是只读文件，run workspace 需要完整 tree/commit 与自己的 run 分支；复用会把两种生命周期和清理策略绑在一起。
- **把凭据直接拼进 push URL。** 否决：URL 会进入 git config、缓存和错误上下文，违反凭据不入仓库/数据库的边界。
- **用 admin 诊断接口替代 run 事件。** 否决：事件随 run 持久化，天然带权限与历史；额外接口不增加本 issue 需要的信息，却扩大 API 契约。
- **把 half_open 原样写进事件。** 否决：事件契约只暴露 disabled / closed / open；half_open 实际仍走代理，按 closed 投影，半开状态由 `git.proxy.state` 日志保留。

## Consequences

缓存磁盘占用随访问过的 target + ref 增长，工作区保留策略不清理仓库缓存，需要时人工删除；旧的全量 mirror 目录不迁移也不读取。分支缓存每次 prepare 会做一次 ref fetch 以发现新 commit，完整 SHA 命中后不再联网。恢复路径多一次 run 分支 fetch，换来单 ref 缓存与快进校验的确定性。`gitOperations` 只保留 ls-remote / clone / fetch / push，其他本地 git 子进程仍写结构化日志但不进事件列表。代理探测失败不会改写 run 的 viaProxy 结论；事件与日志的脱敏由统一 sanitize 与主机名提取保证。
