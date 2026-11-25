# Real evaluation: platform gateway factory and SkillOpt-style baseline gate

English | [中文](bugfix-real-eval-platform-gate.md)

```yaml flow
kind: issue
id: bugfix-63
milestone: bugfix
depends:
  - m12-03
priority: P2
status: ready
scope:
  - .github/**
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - deploy/**
  - docs/**
  - fixtures/**
  - plans/**
  - tests/**
  - .agents/**
  - .env.example
adr: []
github:
  number: 620
  url: https://github.com/Shadow-Azure/harness-evolution/issues/620
```

## Background

### Problem

An evolution run still evaluates through placeholder gateways: `fake` returns configured placeholder scores, and the `http` mode targets the generic `/evals` protocol in the design draft, which no real platform implements. Candidate evaluation must move to the real evaluation platform while satisfying four requirements.

- Switching platforms only adds one subclass, registers it in the factory, and changes `.env`; every platform-specific detail stays inside the subclass and upstream code only calls the parent interface.
- Production configures platform options through GitHub Secrets, and the Deploy pipeline injects them into the server `.env`.
- The evaluation metric key is maintained when configuring an evolution target, together with the validation-set and test-set project IDs.
- The evaluation loop follows SkillOpt: the initial version is evaluated once as the baseline, every turn is evaluated once and compared with it, accepted edits build on the accepted Skill, and the baseline becomes the accepted turn's score.

### Current state

- The seam exists but not in the target shape: `EvalGateway` is a `Protocol`, `FakeEvalGateway` lives in the service layer, `HttpEvalGateway` is a dataclass, `build_eval_gateway_factory` selects with an `if mode == "fake"` branch, and legal `HE_EVAL_MODE` values are hard-coded in `config.py`.
- `HttpEvalGateway` and `EvalMapper` speak a fictional protocol: `POST /evals`, camelCase fields, and responses directly carry `currentScore` and `externalVerdict`.
- The decision entry point is `external_verdict == "accept"`. Each turn already has `eval_current` and `eval_candidate`, and the final initial score uses turn 1's `eval_current`. The data model has room for a baseline, but the baseline value is currently assumed to come from the platform.
- Edits already build on the last accepted state: accepting fast-forwards the run branch, rejecting leaves it untouched, and the next candidate branches from the run branch.
- Target configuration already has validation-set and test-set project IDs, snapshotted onto the run, yet no runtime code consumes them.
- Two gaps: the idempotency key omits the attempt count, so a platform-side retry replays the same evaluation; after an `HE_EVAL_*` secret is deleted, the server's stale value still takes effect.

### Evaluation platform contract and production checks

Evaluation platform PR #431 is merged and deployed with every interface needed for machine triggering; the contract direction is HE adapting to the platform, and the platform provides no verdict.

- launch: `POST /api/v1/eval-templates/{template_id}/launch` with a Bearer service token; the body carries `asset_override` (repo_url, ref, commit, asset_paths, asset_types) and `lineage`; a 202 returns `run_id`, `created` and `asset.resolved_commit`.
- status and results: `GET /api/v1/eval-runs/{run_id}/status` exposes 11 statuses and `terminal`; `results` returns metric items only. For the SWE-bench dataset the items are `resolved_rate`, `resolved_rate_scored`, `resolved_count`, `execution_failure_rate`, plus token and cost items.
- Production platform state: all 4 templates bind the OpenSpec-cn asset source, and 3 of them enable self-evolution reporting back into HE; SuperPower is registered only as an asset source with no template; datasets have only 6-case and 1-case versions, and one 6-case turn measured about 34 minutes and 35 USD.
- Candidate repository: measurements confirm GitHub can read a fork-only commit, tree and file content through the upstream repository API, so the subclass does not send `repo_url` and inherits the template's asset source; HE's push fork need not be registered.
- Token: the production frontend has no service-token UI; tokens can only be created through `POST /api/v1/service-tokens` with an admin session and need both `eval:launch` and `eval:read`.

### SkillOpt comparison

The [microsoft/SkillOpt](https://github.com/microsoft/SkillOpt) paper path matches the requirement: before training, evaluate the initial Skill once on the selection set and initialize both `current_score` and `best_score` to it; each step evaluates only the candidate on the selection set and accepts only a strict improvement, after which the current Skill and score become the candidate's, while a rejection changes nothing; finally the initial and final Skills are each evaluated on the held-out test set.

| SkillOpt mechanism | HE today | This issue |
|---|---|---|
| Initial baseline evaluation | Missing | Add run-level baseline evaluation |
| Baseline follows accepted score | Missing | Compute in the service layer from accepted turns |
| Accept only a strict improvement | Trusts the gateway verdict | Platform-neutral gate component |
| Edits build on accepted Skill | Already satisfied | Unchanged |
| Test-set final evaluation | Final only aggregates validation scores | Add test-set final evaluation |

### Discussion record

| ID | Topic | Decision | Status |
|---|---|---|---|
| D1 | Integration shape | Factory plus ABC parent; one subclass per platform registered in the factory and selected by `HE_EVAL_MODE` | Confirmed |
| D2 | Contract direction | HE adapts the platform's launch, status, results and service token; the fictional `/evals` protocol is not kept | Confirmed |
| D3 | Primary metric key location | Target configuration, next to the validation/test project IDs; a project ID is a platform template ID | Confirmed |
| D4 | Register the push fork as an asset source | No; the subclass does not send `repo_url` | Verified |
| D5 | Platform templates | Do not reuse existing templates; create HE-specific validation and test templates with self-evolution reporting disabled | Pending |
| D6 | Token creation | Create through `/api/v1/service-tokens` with an admin session and scopes `eval:launch` and `eval:read` | Verified |
| D7 | Baseline source | Real evaluation: evaluate the initial version once and advance the baseline on acceptance | Confirmed |
| D8 | Baseline and turn 1 | Start in parallel | Confirmed |
| D9 | Acceptance rule | Strictly greater; ties reject; further refinement later | Confirmed |
| D10 | Test-set final | In the first phase | Confirmed |
| P1 | Validation/test set size | Keep the current dataset versions by default; expanding the validation set and adding a held-out test set is recommended | Pending |
| P2 | One primary metric key for validation and test | One shared key by default | Pending |
| P3 | `partial` and `paused_budget` semantics | Add a minimum-completion guard by default; a budget pause directly fails | Pending |
| P4 | Legacy `http` mode | Retire and delete by default | Pending |
| P5 | `knowledge` targets | Not supported in this phase; the subclass rejects explicitly | Pending |
| P6 | Final verdict semantics | Default: there is an accepted turn and the test-final score is strictly better than the test-baseline score | Pending |

## Goals

- Turn the evaluation gateway into a factory with a parent class and subclasses: a new platform only adds a subclass and registration, and `.env`'s `HE_EVAL_MODE` selects the implementation.
- Add an ai-eval-platform subclass encapsulating launch, status, results, error envelopes and service-token details.
- Evaluate the initial version once for a real baseline at run start, in parallel with turn 1's candidate evaluation.
- Decide in the service layer: accept only when the candidate score is strictly better than the baseline, and advance the baseline on acceptance.
- Run the test-set final evaluation after all iterations end.
- Add the primary metric key to target configuration, and snapshot the validation/test project IDs into the run's evaluation configuration.
- Inject GitHub Secrets into `.env` through the Deploy pipeline and keep the docs and `.env.example` in sync.

## Design authority

- [14 §2 Terms and semantics](../../../plans/fullstack-design/14-target-project-ids.md): the validation set drives per-turn candidate decisions and the test set provides final independent acceptance; that slice left the evaluation gateway for later, and this issue is that follow-up.
- [07 §5.7 Evaluation integration and polling](../../../plans/fullstack-design/07-backend-implementation.md): the existing gateway seam and `HE_EVAL_*` fallback; this issue replaces the mode branch with a registry and must update the section.
- [07 §5.8 Applying results, retries and final evaluation](../../../plans/fullstack-design/07-backend-implementation.md): the existing decision, retry and final flow; this issue adds the baseline, gate and test-set final into it.
- [05 §4.11 Evolution target configuration](../../../plans/fullstack-design/05-api-design.md): the target configuration API; this issue adds the primary metric key.
- [06 §5.2 evolution_runs](../../../plans/fullstack-design/06-database-design.md): `eval_config` and project ID snapshots; this issue adds run-level evaluation storage.
- [04 §9 Configuration inventory](../../../plans/fullstack-design/04-backend-architecture.md): `HE_EVAL_*` semantics change with this issue.
- [Agent Note: real patch and evaluation seams](../../../.agents/notes/implemented/architecture/2026-11-17-real-patch-eval-seams.en.md): records the existing mode factory and Secrets channel decisions; this issue updates its facts.
- External references: [evaluation platform PR #431](https://github.com/Shadow-Azure/ai-eval-platform/pull/431), [evaluation platform issue #429](https://github.com/Shadow-Azure/ai-eval-platform/issues/429), [microsoft/SkillOpt](https://github.com/microsoft/SkillOpt).

## Implementation

### Overview

```text
run start
  ├─ baseline        (validation template @ base commit)  ─┐
  ├─ baseline-test   (test template       @ base commit)  ─┤ in parallel
  └─ iteration 1     (validation template @ candidate)     ─┘
iteration N
  candidate eval → gate: candidate > baseline ? accept : reject
  accept  → run branch fast-forwards, baseline := accepted score
  reject  → run branch and baseline stay unchanged
after the last iteration
  final-test (test template @ final commit) → evolution_finals
```

Switching platforms touches only subclasses and the registry; the gate, baseline advance and final evaluation live in the service layer, and subclasses only map protocols and fields.

### Gateway factory

- `third_party_api/eval_gateway/base.py`: `BaseEvalGateway(ABC)` declares `provider`, frozen config, `submit`, `get_status` and `get_result`, and carries sanitized HTTP and error handling.
- `third_party_api/eval_gateway/factory.py`: `EvalGatewayFactory` keeps the registry and offers `register`, `create` and `registered`; assembly creates subclass instances from Settings and the run snapshot.
- `FakeEvalGateway` becomes a subclass of the parent and moves into `third_party_api`, with a re-export at its old location.
- `gateway_factory.py` queries the registry and keeps the `build_eval_gateway_factory(settings)` signature; `config.py` takes legal `eval_mode` values from the registry.
- The old `HttpEvalGateway` and `EvalMapper` retire with the fictional protocol, and stub tests move to the real contract.

### ai-eval-platform subclass

- Submission: `POST /api/v1/eval-templates/{validationProjectId}/launch` with a Bearer service token; `Idempotency-Key` is composed of run, turn sequence, candidate commit and attempt count; the body carries `asset_override`'s commit, ref, asset_paths and asset_types plus `lineage`.
- After submission, assert `asset.resolved_commit` equals the candidate commit and record `warnings` as run events.
- Status mapping: fold the platform's 11 states into HE's 5, and fail explicitly on an unknown state.

| Platform status | HE status | Meaning |
|---|---|---|
| `preparing`, `queued` | `queued` | Waiting |
| `running`, `finalizing`, `cancelling` | `running` | In progress |
| `completed` | `completed` | Fetch results |
| `partial` | `completed` | Guarded by a minimum completion rate; below it counts as failed |
| `failed`, `cancelled` | `failed` | Terminal failure |
| `pausing_budget`, `paused_budget` | `failed` | The platform will not recover; fail with actionable information |

- Results and errors: `results` metric items become measurements verbatim and the service layer picks the primary metric; the error envelope maps to a gateway error carrying the platform error code, where 401, 403, 404 and 422 are not retryable and 5xx, 429 and network errors are retryable.
- Asset mapping: `skill` uses `asset_paths=[subDir]`; `agent` declares `asset_types` as subagent explicitly; `knowledge` is rejected explicitly.

### Baseline, gate and test-set final

- Add a run-level evaluation table for evaluations belonging to no turn: validation baseline, test baseline and test final; its fields mirror the turn evaluation columns, including external ID, status, polling time, attempt count, score and raw metric items.
- Submit the validation and test baselines in parallel right after run creation; turn 1's candidate submits as usual and its decision waits for the validation baseline.
- Gate: turn N's baseline is the latest accepted turn's candidate score, or the validation baseline score when there is none; accept only when the candidate is strictly better under the metric direction, and reject ties.
- `EvalGateway.get_result` returns measurements; the service-layer gate produces `EvalResult` before persistence, and the structure consumed by `apply`, final evaluation and the frontend stays unchanged.
- Submit the test-set final after the last iteration terminates and write `evolution_finals`: the initial score is the test-baseline score and the best score is the test-final score.
- Change the commit message's `Harness-Decision-Rule` and decision wording to the real rule.

### Target configuration, snapshots and contracts

- Add an `evolution_targets.primary_metric_key` column and migration; regenerate the request model, repository and OpenAPI contract.
- On run creation, write `validationProjectId`, `testProjectId`, `primaryMetricKey` and `subDir` into the `eval_config` snapshot, with the wizard's `eval` overrides taking precedence.
- When a real platform is selected without template IDs or the primary metric key, run creation returns 422 pointing at the field.
- Add a "primary metric key" field to the target configuration form and sync list and error copy.

### Configuration, deployment and docs

```text
HE_EVAL_MODE=fake or ai-eval-platform
HE_EVAL_BASE_URL=<platform base URL>
HE_EVAL_API_KEY=<service token; inject via GitHub Secrets only>
```

- Update the three `HE_EVAL_*` descriptions in `.env.example`; the pipeline already injects these keys, so no Secret is added.
- `deploy.yml` explicitly removes the keys when a Secret is empty, so a deleted Secret cannot keep a stale value effective.
- Remove "not yet available: real evaluation" from `docs/architecture.md` and describe the new seam; update `docs/deployment.md` and the deployment manual.
- Agent Note: update the facts in "real patch and evaluation seams" and add a note recording the baseline gate and test-set final decisions.

## Implementation steps

1. Add the run-level evaluation table migration, model and repository, with database tests for both dialects.
2. Migrate `FakeEvalGateway` to a `BaseEvalGateway` subclass, introduce `EvalGatewayFactory`, and keep default behavior identical.
3. Implement the gate component and baseline advance, change `get_result` to return measurements, and route fake mode through the same gate.
4. Implement the ai-eval-platform subclass and real-contract stubs covering submission, the status table, results and error envelopes.
5. Integrate baseline evaluation in parallel with turn 1 and the test-set final at iteration end.
6. Add the primary metric key to target configuration, snapshot template IDs and the metric key onto the run, and regenerate contracts.
7. Update `.env.example`, `deploy.yml`, docs and Agent Notes, and run every gate.
8. Platform operations prerequisite: create validation and test templates, create the service token, configure GitHub Secrets, then acceptance-test with a real run.

## Dependencies and boundary

- Dependency: m12-03 (evaluation gateway seam and the `HE_EVAL_*` Secrets channel), complete.
- Platform-side prerequisites (outside this repository's code scope): validation and test templates with self-evolution reporting disabled, a service token with both scopes, and `HE_EVAL_MODE`, `HE_EVAL_BASE_URL` and `HE_EVAL_API_KEY` in GitHub Secrets.
- Delivery boundary: only HE's gateway, gate, storage, target configuration and deployment docs; the platform's code and templates stay with the platform repository or console.
- "Pending" items are implemented with the discussion record's defaults and adjusted in the same PR after a decision.

## Verification

```sh
pnpm test:api -- -k "eval_gateway or gateway_factory or eval_gate or evolution_evaluations"
pnpm test:db
pnpm contract:check
pnpm verify:flow
pnpm lint:docs
```

- Data: local stubs written against the real platform contract (launch, status and results endpoints, 11 statuses and error envelopes), plus the existing bare remote and seed repository in tests.
- Expected: the baseline and turn 1 candidate evaluations have different idempotency keys and are concurrently in flight after run start; a candidate equal to the baseline is rejected, a better one is accepted and advances the next turn's baseline; rejection leaves the run branch unchanged; the final row carries the test-baseline and test-final scores; fake mode behaves as before.

## Acceptance

- With `HE_EVAL_MODE=ai-eval-platform` the gateway is the registered subclass and an unknown value fails startup; `fake` behaves as before.
- In a real run, the validation baseline and turn 1 candidate evaluation are concurrently in flight, and turn 1's decision comes after the baseline completes.
- Acceptance happens if and only if the candidate is strictly better than the baseline; after acceptance the next turn's baseline equals the accepted candidate score, and rejection leaves the baseline unchanged.
- After submission `asset.resolved_commit` equals the candidate commit; platform 4xx configuration errors enter `blocked(stage=eval)` with the platform error code.
- After the run ends `evolution_finals` records the test-set initial and final scores.
- Target configuration stores the primary metric key and run creation returns 422 when it is missing; the contract does not drift.
- Coverage is at least 80% and the flow and docs gates pass.

## Gates and CI

- Hits: `pnpm test:api`, `pnpm test:db`, `pnpm test:gates`, `pnpm contract:check`, `pnpm lint:api`, `pnpm typecheck:api`, `pnpm verify:flow`, `pnpm verify:flow-online`, `pnpm lint:docs`, `pnpm verify:docs`.
- Add or update an Agent Note in the same PR; no new gate script.

## Non-goals

- Do not change the evaluation platform's code, templates or contract.
- Do not auto-merge; promotion still goes through human PR review.
- Do not refine the acceptance rule: minimum improvement, repeated evaluation and noise handling are later work.
- Do not register HE's push fork as a platform asset source and do not introduce the generic `/evals` protocol.
- Do not write production addresses, tokens or console credentials into the repository.
