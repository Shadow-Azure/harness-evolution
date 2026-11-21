# flow:sync 状态读取恒为 undefined，每次同步重复 PATCH 全部流程对象

[English](bugfix-flow-sync-state-read.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-08
milestone: bugfix
depends: []
priority: P2
status: ready
scope:
  - scripts/flow-sync.mjs
  - scripts/gates.spec.mjs
  - .agents/**
  - plans/**
adr:
  - ../../notes/implemented/bug-fix/2026-11-21-flow-sync-state-read.md
github:
  number: 458
  url: https://github.com/Shadow-Azure/harness-evolution/issues/458
```

## 背景

2026-11-21 关闭 issue #445 时执行 `pnpm flow:sync`：在 `pnpm verify:flow-online` 刚通过、远端与本地没有任何漂移的情况下，命令报告 `状态更新 157`，几乎对每个带编号的 issue 与 milestone 都发了一次状态 PATCH。逐条核对后确认远端状态本身没有被改错（该关的已关、该开的仍开），但每次同步都会对全库流程对象重复 PATCH，消耗 GitHub API 配额，并让“状态更新”计数失去诊断价值、掩盖真实漂移。

复现：在无漂移的 `main` 上连续执行两次 `pnpm flow:sync`，第二次仍会输出与流程对象数量相当的状态更新；同一命令的 `正文更新` 只在对账确实不一致时才增加，说明缺陷只在状态读取与对比这一层。

## 目标

- `readIssueState` / `readMilestoneState` 返回远端真实状态，`runSync` 只对真正不一致的对象发 PATCH。
- 无漂移时重复执行 `pnpm flow:sync` 输出 `状态更新 0`，同步恢复幂等。
- 用门禁自测钉住“远端状态正确解析、无漂移不更新、有漂移才更新”的行为，防止回归。

## 设计依据

- [`.agents/flow/README.md` §GitHub 同步](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/flow/README.md)：`pnpm flow:sync` 是流程树写 GitHub 的唯一入口，按本地状态映射远端（done ↔ closed，其余 ↔ open），因此重复同步必须幂等。
- [`scripts/flow-sync.mjs`](https://github.com/Shadow-Azure/harness-evolution/blob/main/scripts/flow-sync.mjs)：`runSync` 的契约是“读出远端状态，与期望不同才 PATCH”。
- 本 issue 属流程工具链修复，`plans/fullstack-design` 没有对应章节；设计依据取 flow 规则与脚本契约，历史上的 #445 收口操作（PR #453、#456）是本缺陷的真实触发记录。

## 分析定位

**根因**：`scripts/flow-sync.mjs` 的 `gh(args)` 返回 `execFileSync(...).trim()`，是**字符串**，而两个状态读取器把它当成已解析对象来取属性：

```js
readMilestoneState(milestone) {
  return gh(["api", `repos/${repo}/milestones/${milestone.data.github.number}`]).state;
},
readIssueState(issue) {
  return gh(["issue", "view", String(issue.data.github.number), "--repo", repo, "--json", "state"]).state;
},
```

`String.prototype.state` 恒为 `undefined`，于是 `undefined === desired` 永远为 false，`runSync` 对每个带编号对象都调用一次 `updateIssueState` / `updateMilestoneState`。创建路径（`createIssue`）用 `JSON.parse(gh(...))`，正文读取（`readIssueBody`）用 `--jq .body` 拿原始字符串，二者都不受影响，所以缺陷只落在状态对比上；`verify-flow-online` 自己用 `JSON.parse(execFileSync(...))`，在线门禁一直绿，掩盖了问题。

**定位过程**：

1. #445 收口时对比“`verify:flow-online` 绿色”与 flow:sync 的 `状态更新 157`，怀疑状态读取未生效。
2. 审阅 `readIssueState` / `readMilestoneState` 与 `gh` helper 的返回类型。
3. 在 `node` 里复现：对字符串取 `.state` 得 `undefined`，而 `JSON.parse` 后能得到 `"OPEN"` / `"CLOSED"`。
4. 在无漂移的树上连续同步两次，第二次仍报大量状态更新，排除“一次性历史漂移”的解释。
5. 核对远端状态，确认没有错误的开/关，影响只是重复写与计数失真，属于工具缺陷而非状态事故。

## 实现内容

- 状态读取改为解析 JSON：`JSON.parse(gh([...])).state`；或统一改用 `gh api ... --jq .state` 直接拿原始字符串。
- 抽一个 `ghJson(args)`（或给 `gh` 增加 `{ json: true }` 选项）供创建路径与状态读取共用，避免同类把字符串当对象的遗漏。
- 让状态读取器可注入 `gh` 结果，或在 `scripts/gates.spec.mjs` 增加边界测试：当 `gh` 返回原始 JSON 字符串时，读取器必须返回 `OPEN` / `CLOSED` 而不是 `undefined`；同时断言无漂移时 `runSync` 的 `stateUpdates === 0`、有漂移时只计数不一致对象。

## 实施步骤

1. 先写回归测试并确认在现实现下为红：字符串输入 → 读取器返回 `undefined`。
2. 修复读取逻辑（`JSON.parse` 或 `--jq`），测试转绿。
3. 在无漂移的 `main` 上连续执行两次 `pnpm flow:sync`，第二次应输出 `状态更新 0`。
4. 人为制造一个漂移（临时改一个本地 issue 状态或关闭一个远端 issue），确认只 PATCH 该对象且计数为 1。
5. 跑 `pnpm test:gates`、`pnpm verify:flow`、`pnpm verify:flow-online`。

## 依赖与交付边界

- 依赖：`gh` 已认证；无需新增服务、数据库或凭据。
- 交付边界：只改 `scripts/flow-sync.mjs` 与其门禁自测；不改流程状态机、优先级规则、创建/retire 语义，不批量重写远端对象。

## 独立验证

```sh
pnpm test:gates
pnpm verify:flow
pnpm verify:flow-online
# two consecutive syncs without drift: the second must report state updates: 0
pnpm flow:sync
pnpm flow:sync
```

- 修复前：第二次同步的状态更新数约等于流程对象数（2026-11-21 实测 157）。
- 修复后：第二次同步 `状态更新 0`；制造单个漂移时只更新该对象。

## 验收标准

- 无漂移时 `pnpm flow:sync` 的 `状态更新` 为 0，重复执行幂等。
- 有漂移时只 PATCH 不一致的对象，计数与实际一致。
- 门禁自测覆盖“原始 JSON 字符串 → 正确状态”的读取边界，且该测试在修复前为红。
- `pnpm test:gates`、`pnpm verify:flow`、`pnpm verify:flow-online` 全绿。

## 门禁与 CI

- 本地：`pnpm test:gates`、`pnpm verify:flow`、`pnpm verify:flow-online`。
- CI：`docs-flow` lane 会跑 `test:gates` 与 `verify:docs`；`scripts/` 改动按仓库规则同步 `scripts/gates.spec.mjs`，如命令行为变化再同步 `AGENTS.md`。
- 提交与 PR 标题带 `(#N)`；`verify-flow --diff` 校验 scope 覆盖。

## 非目标

- 不重构 flow 工具链，不新增同步子命令或 dry-run 模式。
- 不修改流程状态机、优先级推进与 retiring 逻辑。
- 不清理或重写历史远端 issue / milestone。
- 不处理 2026-11-21 观察到的 E2E `m3-session-browser` 1500x837 bottom gap 偶发失败（另案）。
