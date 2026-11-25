# Agent Note: attribution 平台工具补齐 write_probe_report 的 conclusion/root-cause 契约

Status: implemented

[English](2026-11-25-attribution-writer-conclusion-contract.en.md) | 中文

## Problem

#588（`744f4f57`）给 `attribute-badcases/make_probe_report.py` 增加了两个必需参数 `--conclusion`（`attributed` / `non_target` / `inconclusive`）与 `--root-cause`，并在 `SKILL.md` 里要求 Skill 传入显式结论；但平台侧的 MCP 工具 `CaseTools.write_probe_report(report: ReportFields)` 没有跟进：`ReportFields` 以 `extra="forbid"` 关闭了额外字段，既没有 `conclusion`/`root_cause` 字段，也不会把它们转发给冻结的 writer。结果所有通过平台工具写报告的 attribution 调用都以 `make_probe_report.py` 的 argparse usage 失败，`tests/attribution/test_case_tools.py` 红，`unit-tests-api` lane 红；main 自身 CI 也因此为 failure，但该 PR 仍被合入。另外新脚本要求 `input_badcase.json` 带 `selected_target.name`，而 `test_case_tools.py` 的 fixture 仍是旧形状。

## Decision

`ReportFields` 增加必需字段 `conclusion: Literal["attributed", "non_target", "inconclusive"]` 与非空 `root_cause: str`（blank 由 validator 拒绝），由已有的 `model_dump(exclude_none=True)` 转发循环自动生成 `--conclusion` / `--root-cause`；`test_case_tools.py` 的 fixture 补 `selected_target`，并断言 `probe_report.json` 中的 `conclusion` / `root_cause` 与提交值一致、非法结论/空根因/缺字段均被模型拒绝。writer 的「显式结论」契约保持原样，不引入默认值。

## Alternatives considered

- **平台侧给缺省结论（如 `inconclusive`）**：会让模型漏传时静默产出结论，伪造一条未经判断的归因，破坏 #588 的核心目标。拒绝。
- **把脚本的 `--conclusion` / `--root-cause` 改回可选**：等于回退 #588 的显式结论契约，且 SKILL 已经按必需参数写成正向契约。拒绝。
- **只改测试、不改平台工具**：测试无法合法构造带结论的调用，等于把红门禁改成假绿。拒绝。
- **新建独立 issue + PR 先修 main**：main 的 `unit-tests-api` 红会让每个新 PR 的 CI 同样红，独立 PR 也无法合入；本修复随 #599 的 PR 一起交付，并在 PR 描述与 issue 里单列说明。

## Consequences

- MCP 工具的入参 schema 现在要求 Skill 同时给出显式结论与根因；`SKILL.md`（#588 已更新）与实际契约一致，`case-tools` 模式的 attribution 与启动向导弹窗的绑定计数恢复。
- `unit-tests-api` 恢复绿：`test_case_tools.py` 覆盖平台 writer 的结论透传、输入 `selected_target` 与非法输入拒绝。
- 该修复属于 main 回归而非 #599 的锚点契约，PR 描述与 flow issue 正文中单列一节说明其来源与必要性；不改变 #599 的锚点语义、预算或重试边界。
