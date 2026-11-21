# Agent Note: flow:sync 状态读取解析 JSON

Status: implemented

[English](2026-11-21-flow-sync-state-read.en.md) | 中文

## Problem

`pnpm flow:sync` 在远端与本地没有漂移时会重 PATCH 全部带编号对象：2026-11-21 关闭 #445 时实测 `状态更新 157`。`scripts/flow-sync.mjs` 的 `gh()` 返回 `execFileSync(...).trim()` 的**字符串**，而 `readMilestoneState` / `readIssueState` 把它当解析后的对象取 `.state`；`String.prototype.state` 恒为 `undefined`，与期望状态永远不等，于是每个对象都被判成漂移。同一命令的正文同步只在对账确实不一致时才增加，说明缺陷只在状态读取这一层。`verify-flow-online` 自己用 `JSON.parse` 读远端状态，在线门禁一直是绿的，掩盖了问题。

## Decision

- 状态读取统一先 `JSON.parse`：新增 `githubStateReaders(repo, run)`，返回 `readMilestoneState` / `readIssueState` 两个读取器；`run` 返回 gh 原始 stdout，可注入供门禁自测。`main()` 用真实 `gh` 构造读取器并注入 `runSync` 的 io。
- 新增内部 `ghJson(args)`，创建 milestone、retire 列表与状态读取共用“先解析再取字段”的入口，避免再次把字符串当对象。
- 状态输出解析后必须带非空字符串 `state`，否则直接抛错。缺字段时若静默返回 `undefined`，同步会退化成“永远漂移、每次全量 PATCH”，失败应当响亮而不是浪费配额。
- `scripts/gates.spec.mjs` 新增回归：gh 返回原始 JSON 时读取器返回 `open` / `OPEN`、缺 `state` 时抛错；无漂移时 `stateUpdates === 0`，单个漂移只 PATCH 该对象。

## Alternatives considered

- **只在两个读取器里内联 `JSON.parse`**：能修当下，但读取逻辑仍埋在 `main()` 的 io 字面量里，门禁只能测 `runSync` 的注入桩，测不到真实接线。拒绝；抽成可注入的读取器让接线本身可回归。
- **用 `gh ... --jq .state` 直接取裸字符串**：少一次解析，但把 gh 输出格式与状态比较耦合在参数里，注入缝也要模拟 `--jq` 的输出；同一个脚本里会同时存在两种状态读取形状。拒绝。
- **复用 `verify-flow-online.mjs` 的 JSON 感知 `gh()`**：它属于在线门禁，导出给写入口会让两个脚本互相依赖，职责也倒置。拒绝。

## Consequences

- 无漂移时重复执行 `pnpm flow:sync` 恢复幂等，`状态更新` 计数重新可用于诊断真实漂移。
- `runSync` 的契约与 io 形状未变；issue 正文同步、创建与 retire 路径的行为不变，`ghJson` 只替换等价的 `JSON.parse(gh(...))`。
- 若未来 GitHub 状态字段改名或读取命令改用非 JSON 输出，读取器会抛错而不是静默重复 PATCH；届时应同步修改读取器与门禁自测。
