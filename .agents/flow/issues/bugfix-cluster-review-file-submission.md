# cluster.review 文件提交通道不可用：修复 bare 工具面与 Write 权限规则

[English](bugfix-cluster-review-file-submission.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-30
milestone: bugfix
depends:
  - bugfix-17
  - bugfix-26
  - bugfix-28
priority: P2
status: ready
scope:
  - apps/api/app/third_party_api/ai_agent/**
  - apps/api/app/config.py
  - apps/api/tests/**
  - tests/e2e/**
  - deploy/**
  - .github/workflows/**
  - docs/**
  - plans/**
  - .agents/**
adr: []
github:
  number: 537
  url: https://github.com/Shadow-Azure/harness-evolution/issues/537
```

## 背景

2026-11-23 16:02–16:37，生产连续三个 full run 在聚类阶段失败，错误统一为 `cluster cluster.review failed: AgentProviderError: claude-code analysis call was cancelled`：

| run | 开始时间（CST） | AI 调用耗时 | 提交轮次 | 结果 |
|---|---|---|---|---|
| `01M83PVC3WEHGKDHPYSXWFN19N` | 16:02:39 | 419.378s | 首次约 119s 返回、`submissionRounds=1`、`parseFailures=1`；反馈重试 300s 被杀 | failed |
| `01M83QN546PEXT1VFFDKVMXSKH` | 16:16:44 | 300.362s | `submissionRounds=0`，首次调用就跑满超时 | failed |
| `01M83RHMTRXVYC1KR0BJM4WFNT` | 16:32:17 | 300.363s | `submissionRounds=0`，首次调用就跑满超时 | failed |

三次 run 的 `ai_agent_call` 都是 `task=cluster.review`、`outcome=error`、`model=unknown`、`inputTokens=0`、`outputTokens=0`；`run_failed.error.stage=cluster`。16:02 的第一次调用确实返回了，但没有可解析的 `result.json5`；随后按设计进行的一次反馈重试跑满 300s，被 SIGINT→SIGKILL 终止。16:16 与 16:32 的第一次调用就卡满 300s。

### 问题描述

提交通道要求模型把结论写进任务目录的 `./result.json5`，provider 只允许一个写工具 `Write(./result.json5)`。实际运行的 CLI 是 Claude Code `2.1.323`，analyze 的 argv 同时带了 `--bare`；bare 模式把可用工具收窄为 `Bash / Edit / Read`，**没有 `Write`**。模型写不出提交文件，只能尝试被 `dontAsk` 拒绝的 Bash/Edit，或直接放弃；提交文件必然缺失。缺失触发一次反馈重试，重试继续面对同一个不可用工具面，最终撞上 300s 的 `ANALYZE_TIMEOUT_SECONDS`，被归类为 `cancelled`。

这条链路与进程、权限、模型、网络都无关：CLI 已经能启动（#533 修好了 0700 目录），模型也能正常返回一轮结果，失败点是“提交工具面”和“权限规则”。

为什么必须保留文件通道：`submission.py` 是 provider 无关的提交契约（schema + `result.json5` + collect + 一次反馈重试），后面可能部署到其它环境并切换其它 AI agent/CLI，各家的工具名、权限模型和结构化输出能力差异很大；把 analyze 绑定到 Claude Code 的 `--json-schema` 会让通道失去可移植性。因此本 issue 保留文件通道，只修 provider 侧的 CLI 适配。

### 根因分析过程

1. **读三个失败 run 的事件**：确认 `latencyMs` 分别为 419378 / 300362 / 300363，`submissionRounds` 为 1 / 0 / 0，`submissionParseFailures` 为 1 / 0 / 0；失败发生在 `AI 调用：cluster.review（error）` 之后的 `run_failed`，`stage=cluster`。16:16 与 16:32 的暂停请求发生在调用启动后 2–45 秒，但失败仍精确出现在调用启动后 300s，暂停不取消已启动的 analyze 子进程，可排除。
2. **对比 #533 之前**：10:40 与 14:06 的 run 各有三次 `could not start`（7–10ms、0 tokens），在 degrade 策略下 run 仍 completed；14:22 的 run 在 strict 下同样的 `could not start` 首次显性失败。说明“CLI 起不来”早于本次报错，是 0700 权限缺陷；#533 修复后才轮到提交阶段失败。
3. **读部署日志**：Deploy `45133432394`（15:45）安装/配置 Claude Code `2.1.323`，共享 settings 与 `current` 软链通过 other 位预检；`sudo -u harness` 冒烟因无权限被跳过。16:08 / 16:23 又部署了 `8db62923` / `6d473733`，CLI 版本不变。
4. **读代码**：`claude_code._analyze_argv()` 生成 `--bare … --allowed-tools Write(./result.json5) --no-session-persistence`；`submission.prepare()` 写入 `./schema.json` 并在 prompt 中要求模型读取它、把结论写进 `./result.json5`；`collect()` 只读这个文件。`--allowed-tools` 是允许列表，不是工具提供者；工具不在工具集时，白名单写什么都无效。prompt 还让模型读 `./schema.json`，但 allowlist 没有 `Read`，这是同一处工具面的第二个缺口。
5. **同版本 CLI 复现**：用与生产相同的 `2.1.323` 在本地以同一组 argv 启动，读取 `system/init` 事件（工具列表由 CLI 决定，与模型无关）：`tools=["Bash","Edit","Read"]`；去掉 `--bare` 后工具列表包含 `Write`；`--bare --tools "Read,Write"` 只返回 `Read`，无法把 `Write` 加回来。用完整 analyze 形状的 prompt 运行时，CLI 退出码 0、约 25.7s、`result.json5` 不存在，`permission_denials` 记录被拒的 `Bash` 与 `Edit`，模型结束语明确说“当前可用工具集中没有 Write 工具”。另做一次非 bare 对照：模型确实尝试 `Write`，但 `Write(./result.json5)` 规则没有匹配到任务目录的绝对路径，写仍被拒——说明“相对路径规则”本身也没有被真实验证过；该对照在 macOS 上受 `/tmp` 符号链接影响，最终规则必须在目标 Linux 主机上验证。
6. **核对检视与验收**：PR #514 的检视讨论点 5 已明确指出“analyze 只给 Write、prompt 却让读 schema；`Write(./…)` 模式未在真实 CLI 验证”，结论是推迟到部署机验证；真实 CLI e2e 是 `HE_AI_AGENT_CLAUDE_E2E=1` 的 opt-in，CI 从未执行；单测用 MockRunner 直接写 `result.json5`，看不到真实工具面。issue #521 与 PR #533 的验收都要求“真实 run 的 `cluster.review` 为 `outcome=ok`”，但生产至今没有任何一次成功调用，验收没有真正执行。

### 结论

- 直接原因：`cluster.review` 的 analyze 调用没有产生可解析的提交文件；首次失败后的反馈重试跑满 `ANALYZE_TIMEOUT_SECONDS=300`，被进程组 SIGINT→SIGKILL，归一为 `cancelled`，strict 策略再把 `ClusterAIFailure` 传播成 run failed。
- 根因有两处，必须同时修：① `--bare` 让 CLI 的工具集没有 `Write`，文件通道无法工作；② `Write(./result.json5)` 这类相对路径规则没有匹配调用时的任务目录绝对路径，且 `Read` 不在 allowlist，schema 也不可见。
- #533 是必要修复，不是元凶；#526 让同一失败从静默降级变成显式失败；#514 引入了“文件通道依赖 Write、但没有真实验证工具面”的潜在缺陷。
- 方案：保留文件通道；在 provider 层修好工具面与权限规则，并让“工具不可用”快速、可诊断地失败，而不是烧满 300s。不采用 `--json-schema`。

## 目标

- 让文件提交通道在生产 CLI `2.1.323` 上真正可用：模型能在工具集中看到并调用写工具，权限规则能匹配本次调用的任务目录。
- 提交语义保持 provider 无关：`schema.json`、`result.json5`、collect、一次反馈重试的契约不变；只允许 provider 适配层按 CLI 调整 argv 与工具/权限规则。
- 当提交工具缺失或被拒时，`ai_agent_call` 在数秒内给出可诊断失败（指出缺失工具/被拒路径），不进入 300s 重试；超时/取消时保留有界的 stdout/stderr 与 `permission_denials`。
- 生产验收：真实 run 的 `cluster.review` 为 `outcome=ok`、tokens>0、model 非 `unknown`；`cluster.score` 与 `severity.score` 同样 ok；run 能进入第 6/7 步。

## 设计依据

- [07 §5.5.1 AI Agent 能力面](../../../plans/fullstack-design/07-backend-implementation.md)：analyze 是稳定能力面，工具面与权限模式属于 provider 适配层，不应渗入业务层。
- [07 §5.5.2 三层聚类与任务键](../../../plans/fullstack-design/07-backend-implementation.md)：`cluster.review` / `cluster.score` / `severity.score` 共用 analyze 路径，一处修复覆盖三个任务。
- [07 §5.5.3 六层 JSON 可靠性](../../../plans/fullstack-design/07-backend-implementation.md)：一次性任务目录 + `Write(./result.json5)` + 严格/JSON5/repair 解析 + Pydantic 校验 + 一次反馈重试，是跨后端的提交契约。
- [2026-11-22 真实模型化设计 Note](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/feature/2026-11-22-evolution-real-ai-design.md)：`--bare` 的认证与最小化取舍、`--no-session-persistence`、超时/取消归一。
- [PR #514 检视：讨论点 5](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/2026-11-22-pr514-review.md)：工具面未真实验证的原始记录；本 issue 把“推迟”改成“必须修”。
- [Claude Code 部署说明](https://github.com/Shadow-Azure/harness-evolution/blob/main/docs/claude-code.md)：共享 settings、CLI 版本与 `ANTHROPIC_API_KEY` 的部署边界。

## 实现内容

- **工具面（第一件事）**：在固定 CLI `2.1.323` 上确认一种同时满足“有 `Write`”与“最小上下文/最小权限”的启动方式。候选：
  - 去掉 `--bare`，用显式参数/环境变量保留 bare 原本提供的硬化（禁用 hooks/plugins/CLAUDE.md 自动发现、关闭自动更新等），并验证 init 工具列表包含 `Write`；
  - 若 CLI 没有等价的“保留 Write 的最小模式”，则在 provider 适配层记录该 CLI 的限制，改用“预创建空 `result.json5` + 允许 `Read/Edit`”的文件写入路径，前提是 Edit 的创建语义在同版本真实 CLI 上验证通过；
  - 不允许直接把 `Write` 全局放开或改用 Bash 写文件。
- **权限规则（第二件事）**：按本次调用的 `prep.directory` 绝对路径构造规则；至少允许 `Read(<abs>/schema.json)` 与 `Write(<abs>/result.json5)`（或目录 glob），保持 `dontAsk`，Bash、Edit、任务目录外的写入仍必须被拒。CLI 的绝对路径/`//` 前缀/glob 语法以真实 CLI 验证结果为准，并在 PR 中记录验证输出。
- **快速失败与证据**：解析 CLI result 的 `permission_denials`、`stop_reason`、`num_turns`；如果提交工具不在工具集中或写被拒，直接抛带具体原因的 `AgentProviderError`（不重试、不等待 300s）。超时/取消时保留有界的 stdout/stderr 尾部，`detail` 不再只有 `cancelled`。
- **测试**：单测覆盖 argv/规则构造、工具缺失时的快速失败、被拒写入的诊断；真实 CLI e2e 覆盖“写成功并被 collect”与“越界写入被拒”两个方向；e2e 必须能在 CI 或部署后检查中执行，而不是仅 opt-in。
- **文档与 Note**：更新 `docs/claude-code.md` 的 analyze 工具面/权限说明与验收命令；实现 PR 新增 owning Agent Note，并回填本 issue 的 `adr`。

## 实施步骤

1. 在 `2.1.323` 上复现并固定证据：init 工具列表、无 bare / 等价模式下的工具列表、不同权限规则的匹配结果；把命令与输出贴进 PR。
2. 修改 `claude_code._analyze_argv()` 与工具/规则构造（如需配置项，加到 `Settings`），保持 `submission.py` 的 schema/collect/retry 契约不变。
3. 增加工具面预检与快速失败；补 `permission_denials`/超时证据采集。
4. 新增/更新单测与真实 CLI e2e；把 e2e 接到 CI 或部署后检查；更新文档与 Agent Note。
5. 部署后用一次真实 run 验收：`cluster.review`、`cluster.score`、`severity.score` 均为 `outcome=ok`，tokens>0，model 非 `unknown`，run 进入第 6/7 步。

## 依赖与交付边界

- 依赖：bugfix-17（真实 provider 与提交通道）、bugfix-26（真实 provider 的 strict 失败语义）、bugfix-28（harness 可执行 CLI）。
- 交付边界：`apps/api/app/third_party_api/ai_agent/**`（provider、工具/权限构造、诊断）、`apps/api/app/config.py`（如新增模式/规则配置）、`apps/api/tests/**`、`tests/e2e/**`、`deploy/**`、`.github/workflows/**`、`docs/**`、`plans/**`、`.agents/**`。
- 本 issue 只描述实现契约；实现与验证在后续 PR 完成。实现 PR 的标题与提交必须含本 issue 编号。

## 独立验证

```sh
pnpm test:api -- tests/test_ai_agent_claude_code.py
pnpm test:api
pnpm lint:api
pnpm typecheck:api

HE_AI_AGENT_CLAUDE_E2E=1 \
HE_AI_AGENT_CLAUDE_BIN=/opt/harness/shared/claude-code/current/usr/bin/claude \
  pnpm test:api -- tests/test_ai_agent_claude_code.py -k e2e_real_cli

pnpm verify:docs
pnpm verify:flow
```

- 单测与静态检查全绿；真实 CLI e2e 在 60s 内完成，`result.json5` 被写出并通过 `collect` 校验；越界写入（任务目录之外）被拒。
- 直接探针（部署机）应看到 init 工具列表包含 `Write`，且 `permission_denials` 中没有本次写目标。
- 生产验收：新建一次真实 run，按 `/api/evolution/runs/{id}/events` 检查 `ai_agent_call`：
  - `cluster.review`：`outcome=ok`、`inputTokens+outputTokens>0`、`model != "unknown"`、无 `degraded`；
  - `cluster.score`、`severity.score` 同样 `ok`；
  - run 继续进入第 6/7 步，不再停在 `stage=cluster`。

## 验收标准

- 真实 run 的 `cluster.review` / `cluster.score` / `severity.score` 均为 `outcome=ok`、tokens>0、model 非 `unknown`，`degraded` 不出现。
- run 能进入第 6/7 步；失败不再固定出现在 `stage=cluster`。
- 提交工具缺失或被拒时，调用在数秒内失败，错误 detail 指明缺失的工具或被拒的路径；不再以 300s `cancelled` 作为唯一信息。
- 权限仍是最小面：Bash、Edit（除非作为经验证的创建路径）、任务目录外写入、未声明工具都被拒。
- 文件通道保持 provider 无关：不依赖 `--json-schema`，`submission.py` 的 schema/collect/retry 契约不变。
- 真实 CLI e2e 在 CI 或部署后检查中可重复执行。

## 门禁与 CI

- `pnpm test:api`（含 provider 单测）、`pnpm lint:api`、`pnpm typecheck:api`、`pnpm verify:docs`、`pnpm verify:flow`、`pnpm verify:flow-online`。
- 若 `Settings` 或 API 契约有变化，追加 `pnpm contract:check` 与 `pnpm test:gates`。
- CI lane：`api-static`、`unit-tests-api`、`docs-flow`、`flow-online`；真实 CLI e2e 需要模型/CLI 的 lane 或部署后 smoke，二者至少落地一个。

## 非目标

- 不把 analyze 换成 `--json-schema` 或其它 Claude Code 专有的结构化输出能力；文件通道必须保留。
- 不回退 strict，不恢复静默降级，不改 `cluster_llm` 的失败语义。
- 不放宽权限（不允许全局 `Write`、不允许用 Bash 写提交文件、不允许服务以 deploy 用户运行）。
- 不改聚类 prompt、评分算法、UI 或无关 provider。
- 不在仓库写入生产凭据、Session 内容或私有数据；不按单个问题新开 milestone。
