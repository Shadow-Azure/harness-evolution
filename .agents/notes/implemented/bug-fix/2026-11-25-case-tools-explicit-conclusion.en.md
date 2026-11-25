# Agent Note: adapt the case-tools attribution channel to the explicit-conclusion writer

Status: implemented

English | [中文](2026-11-25-case-tools-explicit-conclusion.md)

## Problem

After `744f4f57`, `origin/main` kept `unit-tests-api` red (4 cases), the `ci-ok` aggregate was red, and every PR was blocked. The root cause was a semantic conflict between two individually green PRs: PR #562 (`f9ad7434`, 03:09Z) added `CaseTools`, which called `make_probe_report.py` with the old writer CLI (`--probe_object`/`--probe_type`/`--attribute-type` and friends); PR #589 (`744f4f57`, 06:21Z) turned the writer into the explicit-conclusion contract (`--conclusion`/`--root-cause` required, repeatable `--evidence-ref`), updated the bubblewrap path and the SKILL instructions, but did not update `CaseTools` or its fixtures. PR #589's CI ran at 02:03Z–02:16Z (base without CaseTools) and merged four hours later; `Protect main` had no required status checks at the time, so the stale green result was trusted. Consequently the case-tools channel was always rejected by the writer with a usage error, and both the bubblewrap and case-tools launch cases timed out.

## Decision

- `CaseTools.ReportFields` gains required `conclusion` (`attributed`/`non_target`/`inconclusive`) and `root_cause`, plus optional `evidence_references`; `probe_object`/`probe_type` become optional and are supplied only when a causal object is identified.
- `write_probe_report` no longer builds flags from `model_dump`; it passes `--conclusion`/`--root-cause`/repeated `--evidence-ref` explicitly and keeps the existing `--probe_object`/`--probe_type`/`--object-version`/proposal semantics. The writer contract and the bubblewrap main path are unchanged. Every argument uses the `--flag=value` form: model-provided text such as `probe_description` may start with `--`, which argparse would mistake for an option in the separated form.
- Both branches of `tests/attribution/case_cli_fixture.py` supply the new arguments; `tests/attribution/test_case_tools.py` asserts that the verdict, root cause, and evidence references reach the report.
- The same PR repairs the main flow-tree drift (`bugfix-56` duplicate → `bugfix-58`; #588 `in-progress` → `done`); otherwise no PR can turn `docs-flow`/`flow-online` green. #605 will rebase and drop the duplicated hunks after this PR merges.
- Repo governance in parallel: `Protect main` now requires `ci-ok` with `strict: true`; the merge queue follows in issue #609.

## Alternatives considered

- **Revert the writer to the old contract**: rejected. Explicit conclusions are the product requirement from #588; reverting would undo the shipped attribution semantics.
- **Fix only the tests, not `CaseTools`**: rejected. The production case-tools channel calls the old contract too; leaving it would only hide an unusable runtime.
- **Split into two PRs (flow repair + code fix)**: rejected. They block each other: the flow PR needs green unit tests to merge, and the code PR needs the flow tree to pass `docs-flow`/`flow-online`; a single repair PR is the only self-consistent path.
- **Use the admin bypass to merge #605 first**: rejected. Bypassing the required checks right after adding them contradicts the governance goal; fixing the code and tests first lets the flow PR rebase normally.

## Consequences

- The case-tools attribution channel regains explicit-conclusion support, the four failing cases pass, and main's `unit-tests-api` can turn green.
- This PR temporarily carries the flow-drift repair; after rebasing, #605 only keeps the AI-agent backend issue file.
- Until the merge queue lands, `strict` still forces a manual rebase plus a full re-run whenever the base moves; that friction is the next governance item in #609.
