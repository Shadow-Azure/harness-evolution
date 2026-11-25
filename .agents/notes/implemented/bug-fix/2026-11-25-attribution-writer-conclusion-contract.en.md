# Agent Note: attribution platform tool catches up with the write_probe_report conclusion/root-cause contract

Status: implemented

English | [中文](2026-11-25-attribution-writer-conclusion-contract.md)

## Problem

#588 (`744f4f57`) added two required arguments to `attribute-badcases/make_probe_report.py` — `--conclusion` (`attributed` / `non_target` / `inconclusive`) and `--root-cause` — and updated `SKILL.md` to require an explicit verdict from the Skill. The platform-side MCP tool `CaseTools.write_probe_report(report: ReportFields)` did not follow: `ReportFields` forbids extra fields and had neither `conclusion` nor `root_cause`, so the tool could not accept or forward them to the frozen writer. Every attribution run that submitted a report through the platform tool therefore failed on the script's argparse usage, `tests/attribution/test_case_tools.py` was red, the `unit-tests-api` lane was red, and main's own CI was a failure even though that PR merged. The new script also requires `input_badcase.json` to carry `selected_target.name`, while the `test_case_tools.py` fixture still had the old shape.

## Decision

`ReportFields` gains the required `conclusion: Literal["attributed", "non_target", "inconclusive"]` and a non-blank `root_cause: str` (blank rejected by a validator); the existing `model_dump(exclude_none=True)` forwarding loop then emits `--conclusion` / `--root-cause` automatically. The `test_case_tools.py` fixture gains `selected_target`, and the test asserts the persisted `probe_report.json` carries the submitted `conclusion` / `root_cause`, while invalid verdicts, blank root causes, and missing fields are rejected by the model. The writer's explicit-verdict contract stays as-is; no defaults are introduced.

## Alternatives considered

- **Default the platform-side verdict (e.g. `inconclusive`)** would silently fabricate an unattributed verdict when the model omits one, breaking #588's core goal. Rejected.
- **Make `--conclusion` / `--root-cause` optional again** would revert #588's explicit-verdict contract even though `SKILL.md` already states them as required. Rejected.
- **Fix only the test, not the platform tool** cannot legally construct a verdict-bearing call and would turn a red gate into a fake green. Rejected.
- **Open a separate issue and PR to fix main first**: with `unit-tests-api` red on main, every new PR's CI would also be red, so the separate PR could not merge either; the fix ships with the #599 PR and is called out in the PR description and the flow issue. Rejected.

## Consequences

- The MCP tool's input schema now requires the Skill to provide both the explicit verdict and the root cause; `SKILL.md` (updated in #588) matches the actual contract, and `case-tools` attribution plus the launch-wizard binding counts recover.
- `unit-tests-api` returns to green: `test_case_tools.py` covers verdict forwarding, the `selected_target` input, and rejection of invalid inputs.
- This fix addresses a main regression, not #599's anchor contract; the PR description and flow issue body state its source and necessity, and #599's anchor semantics, budget, and retry boundaries are unchanged.
