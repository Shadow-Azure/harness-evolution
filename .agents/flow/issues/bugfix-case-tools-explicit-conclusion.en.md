# Fix the contract mismatch between the case-tools attribution runtime and the explicit-conclusion writer

English | [中文](bugfix-case-tools-explicit-conclusion.md)

```yaml flow
kind: issue
id: bugfix-60
milestone: bugfix
depends: []
priority: P2
status: ready
scope:
  - apps/api/app/third_party_api/ai_agent/**
  - apps/api/tests/**
  - .agents/**
  - plans/**
  - docs/**
adr: []
github:
  number: 608
  url: https://github.com/Shadow-Azure/harness-evolution/issues/608
```

## Background

### Symptom

`origin/main` has kept `unit-tests-api` red since `744f4f57` (4 cases); main's own push CI fails the same way, the `ci-ok` aggregate is red, and every PR is blocked:

- `tests/attribution/test_case_tools.py::test_only_platform_writer_chooses_paths_and_case_identity` — `ValueError: platform writer rejected the report: usage: make_probe_report.py ... --input-badcase ... --bad-case-id`.
- `tests/m5-05-launch-wizard/test_launch_api.py::test_startup_claims_existing_binding_with_shared_provider` — expected `(generation, 0)`, got `(generation, 1)`.
- `test_local_attribution_from_wizard_to_cluster[bubblewrap-bound-bubblewrap]` / `[case-tools-other-case-tools]` — TimeoutError.

### Root cause: two individually green PRs conflicted semantically at merge time

- `f9ad7434` (PR #562, merged 03:09Z) added `apps/api/app/third_party_api/ai_agent/attribution_case_tools.py` (the MCP tool channel used on Linux without bwrap) and `tests/attribution/test_case_tools.py`. That channel calls `attribute-badcases/make_probe_report.py` with the **old writer CLI**: only `--probe_object` / `--probe_type` / `--attribute-type` / `--probe-description` / `--probe-analysis` and friends.
- `744f4f57` (PR #589, merged 06:21Z) turned the writer into the **explicit-conclusion contract**: `--conclusion` and `--root-cause` became required, repeatable `--evidence-ref` was added, and the bubblewrap path (`canonical_report`) plus the SKILL instructions were updated; `CaseTools`, `tests/attribution/case_cli_fixture.py`, and `tests/attribution/test_case_tools.py` were **not** updated.
- PR #589's CI ran at 02:03Z–02:16Z on head `6adde1d4`, when the base did not yet contain the CaseTools work from `f9ad7434`, so it was green; it merged four hours later against a base that did contain it, and the repo had **no required status checks**, so the stale green result was trusted (that configuration gap is now closed by the `Protect main` ruleset; the merge-queue follow-up issue tracks the systematic fix).

Result: the case-tools attribution runtime (and the fixture CLI used by the bubblewrap tests) still calls the new writer with the old CLI, the writer rejects it with a usage error, attribution batches fail, and the launch tests time out.

### Impact

- On Linux deployments with `HE_ATTRIBUTION_BWRAP_ENABLED=false` or without bubblewrap, the attribution path is unusable (`CaseTools.write_probe_report` is always rejected by the writer).
- Main CI is red and blocks every PR.

## Goals

- Adapt `CaseTools` to the explicit-conclusion writer: `ReportFields` gains `conclusion` (`attributed` / `non_target` / `inconclusive`, required), `root_cause` (required), and `evidence_references` (optional list); pass `--conclusion` / `--root-cause` / repeated `--evidence-ref`, keeping the existing semantics of `probe_object` / `probe_type` / `object_version` / proposal options.
- Update `tests/attribution/case_cli_fixture.py` so both the sandbox and case-tools fixtures supply the new required arguments and evidence references.
- Update `tests/attribution/test_case_tools.py` fields and assertions (verdict, root cause, and evidence references reach the report).
- Restore the four failing cases to green without changing the bubblewrap path or the writer contract.

## Design authority

- [07 §5.5.3](../../../plans/fullstack-design/07-backend-implementation.md): the submission channel and the platform writer are deterministic collection contracts; a writer contract change must update every caller.
- [attribute-badcases/make_probe_report.py](../../../attribute-badcases/make_probe_report.py): the single source of truth for the explicit-conclusion CLI (required `--conclusion`/`--root-cause`/`--evidence-ref`, and the `--probe_object` / `--object-version` cross-field rule).

## Implementation

- `attribution_case_tools.py`:
  - `ReportFields` gains `conclusion: Literal["attributed","non_target","inconclusive"]`, `root_cause: str`, and `evidence_references: list[str] = []`; `extra="forbid"` stays.
  - `write_probe_report` argument assembly: `--conclusion`, `--root-cause`, one `--evidence-ref` per reference; `attribute_type`/`probe_description`/`probe_analysis` keep `--attribute-type`/`--probe-description`/`--probe-analysis`; `probe_object`/`probe_type` stay underscore-form, `object_version` uses `--object-version`, proposals use `--proposal-*`, and `detail_description` uses `--detail-description`.
  - Reading the case row is unchanged (`bad_case_id` remains platform-owned).
- `case_cli_fixture.py`: the sandbox branch adds `--conclusion attributed --root-cause ... --evidence-ref L1`; the case-tools branch adds `conclusion`/`root_cause`/`evidence_references` to the `report` argument.
- `test_case_tools.py`: the success case asserts `conclusion`/`root_cause`/`evidence_references` reach the report; a `probe_object` differing from the selected target without `--object-version` is still rejected; receipt and symlink-guard assertions stay unchanged.
- Docs: when the writer contract is described in docs, note that the case-tools channel follows the same explicit-conclusion contract.

## Implementation steps

1. Change `ReportFields` and the `write_probe_report` argument mapping; run `test_case_tools.py`.
2. Change both `case_cli_fixture.py` calls; run the two parameterized `test_launch_api.py` cases.
3. Run the focused cases and `pnpm test:api -- -k "case_tools or local_runtime or launch_api"` to confirm the four failures are gone.
4. Run `pnpm lint:api`, `pnpm typecheck:api`, `pnpm test:gates`; commit and open the PR.

## Dependencies and boundary

- Dependencies: none (`bugfix-57`/`bugfix-58` are unrelated).
- Boundary: only `ai_agent/attribution_case_tools.py` and the related test fixtures/cases; no changes to the writer contract, the bubblewrap/`local_attribution` main path, the report structure, or business verdict semantics.

## Verification

```sh
pnpm test:api -- -k "case_tools or local_runtime or launch_api"
pnpm test:api -- -k "m5_05 or attribution"
pnpm lint:api
pnpm typecheck:api
```

- Expected: `test_case_tools.py` is green; both the `bubblewrap` and `case-tools` parameterized `test_launch_api.py` cases pass; the `probe_reports` row count and attribution-log assertions are restored; main's `unit-tests-api` turns green.

## Acceptance

- A report produced by `CaseTools.write_probe_report` contains `conclusion`/`root_cause`/`evidence_references`, and the writer exits 0.
- The four failing cases pass again; `tests/attribution` and `tests/m5-05-launch-wizard` do not regress.
- The writer's required-field and cross-field rules are unchanged; a `probe_object` differing from the selected target still requires `--object-version`.
- Focused gates and `test:gates` pass; no new dependencies.

## Gates and CI

- Hit: `pnpm test:api`, `pnpm lint:api`, `pnpm typecheck:api`, `pnpm test:gates`, `pnpm verify:flow`.
- CI uses fake/stub providers and the fixture CLI; no network and no real `claude` binary.

## Non-goals

- No changes to the `make_probe_report.py` CLI or report structure; no restoration of old-field compatibility.
- No changes to the bubblewrap main path, the `local_attribution` verdict logic, or the clustering logic.
- No relaxing of `ReportFields.extra="forbid"` or the path guards.
