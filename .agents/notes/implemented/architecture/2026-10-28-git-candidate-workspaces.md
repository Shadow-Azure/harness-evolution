# Agent Note: 自进化 Git workspace 与 candidate 生命周期

Status: implemented

[English](2026-10-28-git-candidate-workspaces.en.md) | 中文

## Problem

启动向导此前只会创建 `preparing` run 和占位的 prepare job；它既不校验引擎注册表，也不会 clone 冻结版本、建立 run 分支、写筛选/聚类/归因/排序状态或生成可评测的 candidate。缺少这些真实边界时，运行详情只能显示 fixture，无法证明 candidate 来源、远端位置和接纳后的 fast-forward 关系。

## Decision

启动在写库前通过 `EngineFactory.is_registered` 校验 `engine_key`，未注册值返回 `422 ENGINE_INVALID`。真实 prepare 按冻结的 run 快照读取 probe，复用现有查询、聚类和演进仓储：完整模式先建立隔离 workspace 与 `evo/{YYYYMMDD}-{run_id}` 分支，再以独立事务完成聚类、簇级置信度和严重度/rank，按 rank 创建轮次并把 run 推入 `running`；cluster-only 只完成前两步的只读事实，不 clone 或建轮次，随后进入 `completed`。

Git 操作只通过 argv 进程边界执行，禁用 terminal prompt，所有诊断先脱敏再进入日志/事件。cache 是 `data/repos/{target_id}` 的 mirror，run workspace 是 `data/workspaces/{run_id}`；mirror 的 origin 与 run 当前 `repo_url` 不一致时整体重建，避免把旧仓库对象发布到新远端。sub dir、ref、base commit、run 分支、clean state、父链和 trailer 在每次发布前校验；`HE_GIT_PUSH=false` 时所有远端写入统一跳过，仅保留本地生命周期。candidate 内容由确定性占位 patch 真实落盘并 commit，message 固定包含问题、分析、改动、追溯和 `Harness-Run-Id` 等 trailer；推送最多立即重试三次、间隔五秒，失败同时持久 `push_failed` 与 `blocked(push)` 并保留 candidate。

Git 的 ref 命名空间不允许 `evo/{date}-{run}` 同时作为 `refs/heads` 分支和其更长路径的前缀。因此设计要求的可见 candidate ref 保持在 `evo/{date}-{run}/candidate/rN`，实际存储于 `refs/tags`；本地工作分支使用哈希化名称。这样接受时仍可对 candidate 执行精确 `--force-with-lease`，随后切回 run 分支、只允许 fast-forward、非 force 推送并删除 candidate tag；拒绝时只删除 candidate tag/本地临时分支，run 分支和已接纳轮次不变。accepted/rejected 是吸收态，相反方向或再次改写返回 stage conflict。

prepare handler 结束后，组合根通过 terminal lifecycle 自动排队 `evolution_advance`，由生产 handler 从真实持久轮次发布第一轮 candidate；持久层用条件更新原子 claim 一个 pending 轮次，前序轮次仍为 patching/pushing/evaluating/deciding/failed 时后续 pending 轮次不会越序，accepted/rejected 后才解锁下一轮，并发或重复 advance 也只允许一次发布。该 hook 仍先释放既有 sync job 锁，并执行保留活动 run 的 workspace 清理。prepare 的 0–4 cursor 每个 checkpoint 都可恢复，轮次插入和最终 `running` 标记在重试时不会重复候选或覆盖已接纳分支。

## Alternatives considered

直接把 candidate 建成 run 分支的子分支会被 Git 的文件/目录 ref 冲突拒绝；改写 candidate 可见名会违背设计、UI 和既有契约；把 run 分支和 candidate 都改成 force push 会让已接纳历史可被覆盖。集中放在调用方做 workspace、patch 和 Git 校验会让未来引擎绕过 branch/base/clean/trailer 边界，因此这些校验留在统一 Git workspace 服务。

## Consequences

prepare、candidate 和接纳/拒绝现在都有真实文件、commit、远端 ref、持久轮次与事件证据，可用临时 bare remote 完整复现。run 分支初始建立即发布，candidate tag 承载每轮临时对象；m5-10 仍需在 evaluation 完成后继续下一轮并决定终态，m5-11 仍需自动退避和崩溃恢复。V1 patch、confidence 和评测分数仍为占位，但执行路径、状态机和安全边界是真实实现。
