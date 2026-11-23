# PR 流水线耗时 18–20 分钟：unit-tests 串行执行 1724 个 API 测试的成因与并发化方案

[English](bugfix-ci-unit-tests-duration.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-07
milestone: bugfix
depends: []
priority: P2
status: done
scope:
  - .github/workflows/**
  - apps/api/pyproject.toml
  - apps/api/tests/**
  - scripts/run-api.mjs
  - scripts/gates.spec.mjs
  - package.json
  - pnpm-lock.yaml
  - apps/web/vitest.config.ts
  - docs/**
  - plans/**
  - .agents/**
  - AGENTS.md
adr: []
github:
  number: 445
  url: https://github.com/Shadow-Azure/harness-evolution/issues/445
```

## 背景

### 问题场景

2026-11-20 的 PR #432 合并前 CI（[run 44693742962](https://github.com/Shadow-Azure/harness-evolution/actions/runs/44693742962)）从 workflow 触发到 `ci-ok` 结束共 18 分 10 秒，其中 `unit-tests` 占 18 分 01 秒；同一运行的 `e2e` 8 分 14 秒、`docs-flow` 2 分 21 秒，其余 lane 均在 2 分钟内。`ci-ok` 是分支保护唯一 required check，必须等全部 lane，因此 PR 的可合并时间由最长的 `unit-tests` 决定，而不是由全仓门禁的实际工作量决定。

同一时段另外两次成功运行分别是 20 分 39 秒和 19 分 45 秒；当天最近 8 次成功运行的 `unit-tests` 落在 13–21 分钟。长反馈窗口期间新提交还会触发 `cancel-in-progress`，06:16–07:47 有 8 次 run 在 4–14 分钟被取消，重复消耗 runner 时间。

| Run | 事件 | unit-tests | 其余最长 lane | CI 总时长 |
|---|---|---:|---:|---:|
| 44693742962 | PR #432 合并前 | 18:01 | 8:14（e2e） | 18:10 |
| 44693782397 | 同分支重跑 | 20:39 | 6:41（e2e） | 21:07 |
| 44690928979 | main push | 19:45 | 6:50（e2e） | 19:54 |

### 耗时构成

以 run 44693742962 的 `unit-tests` job 日志为准，18 分 01 秒的构成如下：

| 阶段 | 日志时间 | 耗时 | 占 job |
|---|---|---:|---:|
| checkout + pnpm install + Python venv | 07:16:26–07:16:54 | 28s | 2.6% |
| Web vitest（101 文件 / 766 用例） | 07:16:55–07:17:42 | 47s | 4.3% |
| API pytest + coverage（1724 通过 / 22 跳过） | 07:17:42–07:34:24 | 16:37 | 92.2% |
| 覆盖率汇总与 job 收尾 | 07:34:25–07:34:27 | <1s | <0.1% |

- Web 测试已经是并行的：vitest 默认 worker 池，766 个用例 47 秒跑完，不是瓶颈。
- API 测试是单进程串行：`pnpm test` → `test:api` → [`scripts/run-api.mjs`](https://github.com/Shadow-Azure/harness-evolution/blob/main/scripts/run-api.mjs#L32-L34) → `pytest.main([])`，没有 `-n` 或 xdist；1724 个用例挤在一个进程里，996.87 秒意味着平均 0.58 秒/用例。
- 标准 GitHub 托管 Ubuntu runner 是 4 vCPU，API 阶段实际只用一个核；本机 10 核同套用例串行 321.0 秒（0.19 秒/用例），`-n 4` 首次 117.6 秒（2.7×）、连续复跑 129–165 秒，说明并发是可用杠杆，但需要先修计时用例。

### 为什么串行会放大到 18 分钟

1. **单进程没有并发**：pytest 一次只跑一个用例，`pnpm test` 又用 `&&` 串起 web 和 api，web 的 47 秒也只能等 API 结束后才开始，两个套件在关键路径上相加而不是重叠。
2. **大量用例重建应用并跑完整迁移**：测试里 `create_app` 出现 132 次、`upgrade_database` 出现 120 次；[`create_app` 的 lifespan](https://github.com/Shadow-Azure/harness-evolution/blob/main/apps/api/app/main.py#L465-L485) 每次都执行 24 个 Alembic revision。本机一次全新 SQLite upgrade 0.51 秒，上百次测试建库累计是分钟级固定开销。
3. **密码哈希按默认成本重复执行**：[`IdentityService`](https://github.com/Shadow-Azure/harness-evolution/blob/main/apps/api/app/service/identity/service.py#L30) 和 [`PasswordProvider`](https://github.com/Shadow-Azure/harness-evolution/blob/main/apps/api/app/service/identity/password.py#L19-L20) 每个实例都构造 `PasswordHasher` 并计算一次 dummy hash；132 处建 app 调用就重复同样的成本，本机单次约 42ms。生产参数不能降，但测试可以注入低成本 hasher。
4. **单元 lane 混入真实进程与真实等待**：[`test_git_workspace.py`](https://github.com/Shadow-Azure/harness-evolution/blob/main/apps/api/tests/m5-09-git-candidate/test_git_workspace.py#L1085) 起真实 git 子进程并有 4.5 秒 `sleep`，`m12-03` 走真实 patch/eval，`m12-01` 起 HTTP 上游；33 处 fixture 调用重建 corpus 或外部表，一次运行产生 3691 条 warning。慢测试 top 40 合计约 53 秒（本机），其余约 83% 是分布式的启动、迁移与清理成本。
5. **同一批数据库用例跑两遍**：`tests/test_database.py` 的 33 个用例既在 `unit-tests` 里跑，又在 `db-sqlite` lane 里跑一次；后者 51 秒完成，unit lane 内的同一批用例没有新增覆盖价值。
6. **超时与反馈窗口掩盖回归**：`unit-tests` 的 timeout 是 30 分钟，18–20 分钟被认为是“正常”；没有 `--durations` 摘要，新增慢用例不会在 CI 上暴露，只会继续推高墙钟。

结论：主因是 API 套件缺少并发与每用例固定启动成本过高，不是个别慢文件；把 web 拆出去只能省 47 秒，单靠拆 job 不够。

## 目标

- 在标准 4 vCPU runner 上把 `unit-tests` 墙钟从 18–20 分钟降到 ≤8 分钟，全 CI ≤10 分钟。
- 保持完整套件：1724 个 API 用例、766 个 Web 用例与 22 个 skip 一个不少，不加路径过滤、不跳过 lane。
- 保持覆盖率口径：API ≥90%（branch），Web ≥80%（branches/functions/lines/statements）。
- 连续 3 次 PR 运行稳定，p95 `unit-tests` ≤8 分钟；出现隔离性 flake 时能定位并可单独复跑。
- CI 摘要能区分 setup、web、api 三段耗时，并列出最慢用例，后续回归可见。

## 设计依据

- [AGENTS.md 开发流程](https://github.com/Shadow-Azure/harness-evolution/blob/main/AGENTS.md#L67)：行为变更同步单测与跨栈集成，CI 必须执行测试，覆盖率不得低于 80%。
- [03 §前端测试运行](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/03-frontend-architecture.md#L290)：`pnpm test` 跑全部，CI 与本地共用同一份 `vitest.config.ts`；拆 job 不能改变测试集合与配置。
- [04 §数据库与 CI](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/04-backend-architecture.md#L195)：SQLite 快跑与 MySQL `-m mysql` 集成测试分两条，现有 lane 划分保留。
- [09 R8 跨库差异](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/09-review-guide.md#L138)：双库 CI 是既定门禁，`db-sqlite` 与 `mysql` lane 不合并、不跳过。
- [run-api.mjs 覆盖率包装](https://github.com/Shadow-Azure/harness-evolution/blob/main/scripts/run-api.mjs#L32-L34)：coverage 在 pytest 主进程里 start/stop，xdist 的 worker 不在该进程内，直接加 `-n` 会漏计覆盖率，必须换成可合并的收集方式。
- [2026-10-28 CI 拆分 lane 的 Agent Note](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/process/2026-10-28-ci-lane-split.md)：当时以“拆 web/api 需要跨 job 覆盖率聚合”为由拒绝；实际上 [Web 阈值 80](https://github.com/Shadow-Azure/harness-evolution/blob/main/apps/web/vitest.config.ts#L12-L17) 与 [API 阈值 90](https://github.com/Shadow-Azure/harness-evolution/blob/main/apps/api/pyproject.toml#L41-L45) 本来就按套件分别判定，拆分不需要聚合，旧理由需要按本 issue 的证据修正。
- [ci.yml 的 unit-tests job](https://github.com/Shadow-Azure/harness-evolution/blob/main/.github/workflows/ci.yml#L44-L66)：单 job 同时装 Node 与 Python、串行跑 web+api、timeout 30 分钟，是当前关键路径的物理位置。

## 实现内容

- 把 `unit-tests` 拆成 `unit-tests-web` 与 `unit-tests-api` 两个 job，并行执行；两者都进 `ci-ok` 的 `needs`，任一失败仍一票否决，Web 不进入 API 关键路径。
- 在 `apps/api/pyproject.toml` 的 dev 依赖加入 `pytest-xdist` 与 `pytest-cov`；CI 显式用 `-n 4`（标准 runner 4 vCPU），本地可用 `-n auto`，并保留 `test:api:serial` 供隔离问题排查。
- 用 pytest-cov 替代 `run-api.mjs` 里的手写 coverage 包装：`--cov=app --cov-branch --cov-report=term-missing --cov-fail-under=90`，pytest-cov 自动合并 xdist worker 的数据，阈值仍是 90%。
- 并发化前先硬化计时敏感用例：`test_git_timeout_terminates_the_process_group_before_returning` 在 `--dist loadscope` 与默认分发下各复现 1 次 `process-started` 未创建的失败；把固定 `sleep(4.5)` 与 2 秒超时改成事件等待/轮询，并把真正依赖真实进程的用例标记为串行阶段。
- 用 `--dist load` 作为默认分发，先验证模块级状态；若某模块必须同 worker，再用 `--dist loadscope` 并按模块补齐隔离，不能靠全局串行回避。
- Phase 2 降低每用例固定成本：用 session 级模板库（迁移一次后按测试复制文件）或 `create_app(run_migrations=False)` 测试缝，避免 120 次重复 Alembic upgrade。
- Phase 2 注入低成本 `PasswordHasher`（仅测试配置，生产默认不变），并避免在每次构造时重复计算 dummy hash。
- 在 CI 输出 `--durations=25`，把 setup/web/api 三段耗时写进 job summary；先作为可见性与软告警，不直接设硬阈值，稳定后再收紧。

## 实施步骤

1. 记录基线：串行 `pytest -q`、`-n 4`、`--durations=25` 的墙钟、通过/跳过数和覆盖率，固化到 PR 描述。
2. 加入 pytest-xdist 与 pytest-cov，本地连续跑 3 次 `-n 4`，确认通过/跳过数与覆盖率与串行一致。
3. 修复并发暴露的计时/隔离问题，至少覆盖已复现的 git timeout 用例；无法并行的用例单独标记并放到串行补跑阶段。
4. 修改 `ci.yml` 拆出 web/api 两个 job，接入 `ci-ok`，API 用 `-n 4`，保留现有 timeout 语义并分别设置合理上限。
5. 在 PR 上连续观察 3 次真实 CI，记录 `unit-tests` 与全 CI 墙钟；按结果调整 `-n`、`--dist` 或 job 上限。
6. 若仍未达到 ≤8 分钟，执行 Phase 2 的模板库与低成本 hasher；文档命令与门禁同步更新，并把实测数据补回本 issue。

## 依赖与交付边界

- 依赖：标准 4 vCPU GitHub 托管 runner、PyPI 可安装 `pytest-xdist`/`pytest-cov`；不需要新增服务、数据库或外部凭据。
- 交付边界：只改 CI 与测试基础设施；不改应用行为、生产哈希参数、数据库 schema；不删除或跳过任何现有用例。
- 协调点：若 xdist 的隔离问题在合理努力内无法稳定，fallback 是按套件跨 runner 分片，但那需要 coverage artifact 合并且 CI 分钟数成倍增加，必须另案评估，不作为本 issue 首选。

## 独立验证

```sh
cd apps/api
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest -q -n 4 --durations=25
cd ../..
pnpm test
pnpm verify:flow
pnpm verify:docs
```

| 方式 | 命令 | 墙钟 | 结果 |
|---|---|---:|---|
| 串行基线 | `pytest -q` | 321.0s | 1724 通过 / 22 跳过 |
| 4 worker 默认分发 | `pytest -q -n 4` | 117.6–165.1s | 4 次中 3 次全绿，1 次计时 flake |
| 4 worker loadscope | `pytest -q -n 4 --dist loadscope` | 141.1s | 1 个计时 flake |

- 本机为 10 核 macOS、Python 3.12.14、pytest 8.4.2、xdist 3.8.0；连续 3 次 `-n 4` 为 151.1s、165.1s、129.4s，其中第 2 次在同一 git timeout 用例失败，说明硬化该用例是并发化的前置条件。数据只作相对比较，CI 侧以 4 vCPU 上连续 3 次真实运行为准。
- 并发后通过/跳过数必须与串行一致，API 覆盖率 ≥90、Web 覆盖率 ≥80；任一不满足即视为未完成。
- CI 侧预期 API 从 16:37 降到 6–8 分钟、`unit-tests` job ≤8 分钟；若 3 次中任一次超过 8 分钟，继续调 `-n`/分发或执行 Phase 2，而不是调高验收线。

## 验收标准

- 连续 3 次 PR 运行的 `unit-tests` ≤8 分钟、全 CI ≤10 分钟，且 `ci-ok` 仍能正确聚合两个新 job。
- API 1724 通过 / 22 跳过、Web 766 通过 / 1 跳过保持不变；API 覆盖率 ≥90%，Web ≥80%。
- 已复现的 git timeout 计时用例在 `-n 4` 下连续 3 次通过；没有新增隔离性 flake。
- CI 摘要包含 setup/web/api 三段耗时与 `--durations=25`；PR 描述带前后对比表、run 编号与实测命令。
- 若 Phase 2 暂缓，issue 保持打开并记录剩余耗时与瓶颈，不以首期达标代替完整收尾。

## 门禁与 CI

- 本地至少运行 `pnpm test`、`pnpm verify:flow`、`pnpm verify:docs`、`pnpm test:gates`；workflow 改动需人工核对 job 依赖与 timeout。
- PR 标题与每个 commit 标题带 `(#N)`；`verify-flow --diff` 校验本 issue 的 scope 覆盖全部改动文件。
- 分支保护仍只认 `ci-ok`；两个新 job 必须都在 `needs` 中，不允许把 unit-tests 从聚合门里摘掉。

## 非目标

- 不删除、跳过或弱化任何测试，不加路径过滤，不降低覆盖率阈值。
- 不改生产密码哈希参数、应用运行时行为或数据库 schema。
- 不把跨 runner 分片作为首选方案，也不为此引入 artifact 合并设施。
- 不顺手修复与本问题无关的 flaky 测试或重构应用代码。
