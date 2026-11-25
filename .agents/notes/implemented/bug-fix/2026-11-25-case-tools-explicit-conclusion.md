# Agent Note: case-tools 归因通道适配显式结论 writer

Status: implemented

[English](2026-11-25-case-tools-explicit-conclusion.en.md) | 中文

## Problem

`origin/main` 在 `744f4f57` 之后 `unit-tests-api` 持续红（4 个用例），`ci-ok` 聚合红，所有 PR 被阻断。根因是两个各自为绿的 PR 在合并时语义冲突：PR #562（`f9ad7434`，03:09Z）新增 `CaseTools`，按旧 writer CLI（`--probe_object`/`--probe_type`/`--attribute-type` 等）调用 `make_probe_report.py`；PR #589（`744f4f57`，06:21Z）把 writer 改成显式结论契约（`--conclusion`/`--root-cause` 必填、`--evidence-ref` 可重复），同步改了 bubblewrap 路径与 SKILL 指令，却没有更新 `CaseTools` 与 fixture。PR #589 的 CI 跑在 02:03Z–02:16Z（base 尚无 CaseTools），4 小时后才合入；当时 `Protect main` 没有 required status checks，旧绿检查被直接采信。结果是 case-tools 通道必然被 writer 以 usage 错误拒绝，bubblewrap/case-tools 两条 launch 用例超时。

## Decision

- `CaseTools.ReportFields` 增加必填 `conclusion`（`attributed`/`non_target`/`inconclusive`）与 `root_cause`、可选 `evidence_references`；`probe_object`/`probe_type` 改为可选，仅在指认因果对象时提供。
- `write_probe_report` 不再用 `model_dump` 批量拼 flag，而是显式传递 `--conclusion`/`--root-cause`/重复 `--evidence-ref`，并保留 `--probe_object`/`--probe_type`/`--object-version`/proposal 的既有语义；writer 契约与 bubblewrap 主路径不改。所有参数统一用 `--flag=value` 形式：模型提供的 `probe_description` 等文本可能以 `--` 开头，argparse 会把分隔形式的值误判为选项。
- `tests/attribution/case_cli_fixture.py` 的 sandbox 与 case-tools 两个分支同步新参数；`tests/attribution/test_case_tools.py` 断言结论/根因/证据引用进入报告。
- 同一 PR 修正 main 的流程树漂移（`bugfix-56` 重复 → `bugfix-58`；#588 状态 `in-progress` → `done`），否则任何 PR 的 `docs-flow`/`flow-online` 都无法转绿；#605 将在本 PR 合入后 rebase 并去掉重复 hunk。
- 仓库治理同步：`Protect main` 已补 `required_status_checks`（`ci-ok`，`strict: true`）；merge queue 另立 issue #609。

## Alternatives considered

- **把 writer 回退到旧契约**：拒绝。显式结论是 #588 的产品需求，回退会撤销已上线的归因语义。
- **只改测试、不改 `CaseTools`**：拒绝。case-tools 通道在生产上同样按旧契约调用，测试不改只是掩盖生产不可用。
- **拆成两个 PR（流程修复 + 代码修复）**：拒绝。两者互相阻塞：流程 PR 需要单测绿才能合，代码 PR 需要流程绿才能过 `docs-flow`/`flow-online`；合一的修复 PR 是唯一能自洽的路径。
- **用管理员 bypass 先合 #605**：拒绝。刚补上 required checks 就用逃生通道违背治理目标；先修代码与测试，再让流程 PR 正常 rebase。

## Consequences

- case-tools 归因通道恢复显式结论能力，4 个失败用例恢复绿色，main 的 `unit-tests-api` 可转绿。
- 本 PR 临时包含流程漂移修复；#605 rebase 后只保留 AI Agent 后端可替换 issue 文件。
- merge queue 落地前，`strict` 会在 base 前进时要求手动 rebase + 全量重跑，仍有摩擦；这是 #609 要解决的下一个治理项。
