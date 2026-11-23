# Agent Note: CI 单元测试按套件拆 job 并让 API 套件 xdist 并发

Status: implemented

[English](2026-11-20-ci-unit-tests-parallelization.en.md) | 中文

## Problem

`unit-tests` 单 job 串行跑 Web 与 API：Web vitest 101 文件 / 767 用例约 47 秒，API pytest 1739 用例在 4 vCPU runner 上 16 分 37 秒，job 合计 18 分 01 秒；`ci-ok` 等全部 lane，PR 可合并时间由这条最长 lane 决定。API 套件单进程串行，`pnpm test` 又用 `&&` 把两个套件相加；覆盖率由 `run-api.mjs` 在主进程内手写 start/stop，xdist worker 不在该进程，直接加 `-n` 会漏计。并发化还会暴露计时敏感用例：`test_git_timeout_terminates_the_process_group_before_returning` 依赖 2 秒超时与固定 `sleep(4.5)`，在负载高的 worker 上曾因脚本未启动就超时而失败。CI 也没有分段耗时与慢用例摘要，回归不可见。

## Decision

- `ci.yml` 把 `unit-tests` 拆成 `unit-tests-web` 与 `unit-tests-api` 两个并行 job，两者都进 `ci-ok.needs`；Web 10 分钟、API 15 分钟超时，任一失败仍一票否决。
- `apps/api/pyproject.toml` 的 dev 依赖加入 `pytest-xdist` 与 `pytest-cov`。`pnpm test:api` 默认 `-n auto`（本机核数），CI 显式 `-n 8 --dist worksteal`（4 vCPU 上按实测调整：`-n 4` 的 job 7m58s–8m31s、`-n 6` 的 6m05s–8m02s，I/O 等待占比高，继续上探 worker 数以留出验收余量）；`pnpm test:api:serial` 保留串行入口，`--serial` 让单次 `test:api` 串行，用于隔离与计时排查。
- 覆盖率改用 pytest-cov：`--cov=app --cov-branch --cov-report=term-missing`，全量运行时追加 `--cov-fail-under=90`；聚焦路径选择不收集覆盖率（`--no-cov`），避免拿子集覆盖率误判整包阈值。pytest-cov 在主进程合并 worker 数据，API 90% 分支阈值不变；Web 80% 仍由 vitest 自己判定，拆 job 不需要跨 job 聚合。
- 每次 API 测试带 `--durations=25` 并 tee 到日志；`unit-tests-web` 与 `unit-tests-api` 各自把 setup 与套件耗时写入 job summary，API summary 折叠展示最慢用例。先做可见性，不设硬阈值。
- 计时敏感用例改成事件驱动：注入 runner 直接执行脚本（不经过 git 启动），轮询 `process-started`，确认整个进程组已消失，再观察 3 秒副作用窗口；固定 `sleep(4.5)` 删除。
- 分发先用 xdist 默认 `--dist load`；`-n 8` 的实测里出现慢 worker 尾巴（同一 head 的 API job 6m22s / 9m05s / 6m28s），CI 改用 `--dist worksteal` 让空闲 worker 动态接管剩余用例，收敛长尾；若模块级状态要求同 worker，再改 `--dist loadscope` 并补隔离，不退回全局串行。

## Alternatives considered

- 保持单 job、只调 timeout：不解决墙钟，且掩盖回归；否。
- 跨 runner 分片 API 套件：需要 coverage artifact 合并、CI 分钟数成倍；本 issue 明确不作为首选。
- 继续手写 coverage 包装：xdist worker 不在主进程，必须换成 pytest-cov 才能合并覆盖率。
- 把计时用例 skip 或挪进串行补跑阶段：缩小并发覆盖面，且该用例只值几秒；事件等待即可稳定。
- 直接 `--dist loadscope`：并行度更低，且掩盖模块状态泄漏；先验证默认分发。

## Consequences

- API 套件墙钟目标 4–8 分钟；实际收益以 4 vCPU 真实 CI 连续运行为准，Phase 2（session 级模板库、低成本 PasswordHasher）在未达标时另行实施。
- 新增两个 Python 测试依赖，`pnpm-lock.yaml` 不变（Python 依赖不进 pnpm）。
- 默认并发可能暴露未清理的模块级状态；`test:api:serial` 与失败 worker 日志是定位入口。
- `ci-ok` 多一个 needs 项；作业数增加，但两个套件并行，总 runner 分钟数基本不变。
- API job 在 `-n 4` 下三次实测 7m58s–8m31s，贴着 8 分钟验收线；`-n 6` 为 6m05s–8m02s，继续提到 `-n 8` 留余量。若 runner 抖动仍让 job 越过 8 分钟，Phase 2 的模板库是结构性解法。
- 摘要与 `--durations` 是软可见性，稳定后再考虑硬阈值。
