# Real evaluation integration: factory-based eval-platform adapter and a SkillOpt-style baseline gate

English | [中文](bugfix-real-eval-platform-baseline-gate.md)

```yaml flow
kind: issue
id: bugfix-62
milestone: bugfix
depends:
  - m12-03
priority: P2
status: ready
scope:
  - apps/api/**
  - apps/web/src/**
  - tests/**
  - packages/contracts/**
  - docs/**
  - plans/**
  - deploy/**
  - .github/workflows/**
  - .env.example
  - .agents/flow/**
  - .agents/notes/**
  - scripts/doc-budgets.manifest.json
adr:
  - ../../notes/implemented/architecture/2026-11-17-real-patch-eval-seams.md
github:
  number: 620
  url: https://github.com/Shadow-Azure/harness-evolution/issues/620
```

## Background

### Feature request

Evaluation in evolution runs is still a placeholder gateway: `fake` returns the configured placeholder scores, and the `http` mode targets the generic `/evals` protocol from the design draft, which no real platform implements. Candidate evaluation must move to a real evaluation platform and satisfy the four requests below.

- Switching platforms means adding one subclass, registering it in the factory class, and editing `.env`; every platform detail stays inside the subclass, and upstream code calls only through the base-class interface.
- In production, GitHub Secrets hold the platform options and the Deploy pipeline injects them into the server `.env`.
- The evaluation metric key is configured separately for validation and test, maintained together with the two evaluation projects when the evolution target is configured.
- The evaluation loop runs the SkillOpt way: the initial version is evaluated once as the baseline, every candidate is evaluated once after its edit and compared with it, edits after an acceptance build on the accepted Skill, and the baseline becomes the score of the accepted evaluation.

### Current state

- The seam exists but not in the target shape: `EvalGateway` is a `Protocol`, `FakeEvalGateway` lives in the service layer, `HttpEvalGateway` is a dataclass, `build_eval_gateway_factory` selects with an `if mode == "fake"` branch, and the legal `HE_EVAL_MODE` values are hard-coded in `config.py`.
- `HttpEvalGateway` and `EvalMapper` speak a fictional protocol: `POST /evals` and camelCase fields, with a response that returns `currentScore` and `externalVerdict` directly.
- The verdict entry already reads `external_verdict == "accept"`; every iteration carries `eval_current` and `eval_candidate`, and the final evaluation takes the `eval_current` of iteration 1 as the initial score. The data model already reserves a slot for the baseline; only its value is currently assumed to come from the platform.
- Building each edit on the last accepted state already holds: an acceptance fast-forwards the run branch, a rejection leaves it unchanged, and the next candidate still branches off the run branch.
- The target configuration already carries the validation and test project IDs and snapshots them onto the run, but no runtime code consumes them.
- Two gaps: the idempotency key omits the attempt counter, so a retry after a platform-side failure replays the same evaluation, and a deleted `HE_EVAL_*` Secret leaves the stale value active on the server.

### Platform contract and production check

Evaluation platform PR #431 is merged and deployed and provides every endpoint machine triggering needs; the contract direction is that HE adapts to the platform, and the platform returns no verdict.

- Launch: `POST /api/v1/eval-templates/{template_id}/launch` with a Bearer service token; the body carries `asset_override` (repo_url, ref, commit, asset_paths, asset_types) and `lineage`, and 202 returns `run_id`, `created`, and `asset.resolved_commit`.
- Status and results: `GET /api/v1/eval-runs/{run_id}/status` has 11 states plus `terminal`; `results` returns metric items only, and the SWE-bench dataset yields `resolved_rate`, `resolved_rate_scored`, `resolved_count`, `execution_failure_rate`, and the token and cost metrics.
- Production today: all 4 templates bind the OpenSpec-cn asset source and 3 of them enable self-evolution reporting back to HE; SuperPower is registered only as an asset source with no template; the dataset comes in 6-case and single-case sizes only, and one 6-case evaluation took about 34 minutes and 35 US dollars.
- Candidate repository: an experiment confirmed that GitHub serves fork-only commits, trees, and blobs through the upstream repository API, so the subclass sends no `repo_url` and inherits the template's asset source; HE's push fork does not need registration.
- Token: the production frontend bundle contains no service-token UI, so creation goes only through `POST /api/v1/service-tokens` with an admin session; the token needs both `eval:launch` and `eval:read`.

| Check | Result | Impact |
|---|---|---|
| Can the existing templates evaluate candidates directly | No: 3 enable self-evolution reporting, the only one with it off uses the contended spot pool, and every prompt suffix is OpenSpec-specific | The requester creates dedicated validation and test templates for HE in the evaluation platform console |
| Is the SuperPower asset source enough | Yes: fork-only candidate commits are readable through the upstream repository | No need to register the push fork |
| How tokens are created | API only, no UI | Operations creates one with an admin session and stores it in GitHub Secrets |
| Validation-set resolution | With 6 cases the resolve rate moves in 16.7-point steps | The dataset versions will be replaced by the requester on the platform side |

### SkillOpt comparison

The paper path of [microsoft/SkillOpt](https://github.com/microsoft/SkillOpt) matches the request: before training it evaluates the initial Skill once on the selection split and initializes both `current_score` and `best_score` to that result; each step's candidate is evaluated once on the selection split and accepted only when strictly higher than the current score; an acceptance makes the candidate the current Skill and score while a rejection changes nothing; finally the initial and final Skills are each evaluated once on the held-out test set.

| SkillOpt mechanism | HE today | This issue |
|---|---|---|
| Initial baseline evaluation | Missing | Add a run-level baseline evaluation |
| Baseline moves to the accepted score | Missing | Compute in the service layer from accepted iterations |
| Accept only when strictly higher | Trusts the verdict returned by the gateway | Platform-neutral gate component |
| Edits build on the accepted Skill | Already holds | Unchanged |
| Test-set final evaluation | The final evaluation only aggregates validation scores | Add the test-set final evaluation |

### Discussion record

The items below were reviewed with the requester one by one on 2026-11-25, and D5, P1, P2, and P6 were confirmed in a second pass the same day. Items marked pending need a decision before implementation; the plan already states their default values.

| ID | Topic | Conclusion | Status |
|---|---|---|---|
| D1 | Integration shape | Factory class plus ABC base class, one subclass per platform registered in the factory, selected by `HE_EVAL_MODE` | Confirmed |
| D2 | Contract direction | HE adapts to the platform's launch, status, results, and service token, and drops the fictional `/evals` protocol | Confirmed |
| D3 | Where the primary metric key lives | Target configuration, next to the validation and test project IDs; a project ID is a platform evaluation template ID | Confirmed |
| D4 | Register the push fork as an asset source | Not needed; the subclass sends no `repo_url` | Verified |
| D5 | Platform templates | Do not reuse the existing templates; the requester will add dedicated validation and test templates in the evaluation platform console and disable self-evolution reporting | Confirmed |
| D6 | Token creation | Create through `/api/v1/service-tokens` with an admin session; scopes include `eval:launch` and `eval:read` | Verified |
| D7 | Baseline source | Real evaluation: the initial version is evaluated once and the baseline moves with each acceptance | Confirmed |
| D8 | Baseline and iteration 1 | Start in parallel | Confirmed |
| D9 | Acceptance rule | Strictly greater, a tie is rejected, refine later | Confirmed |
| D10 | Test-set final evaluation | Included in the first phase | Confirmed |
| P1 | Validation and test set sizes | Will change: the requester replaces the dataset versions on the platform side later, and HE does not depend on case counts | Confirmed |
| P2 | One metric key or one per project | Not guaranteed to be shared: validation and test each get their own primary metric key | Confirmed |
| P3 | Handling of `partial` and `paused_budget` | Default: a minimum completion guard, and a budget pause fails directly | Pending |
| P4 | The old `http` mode | Default: retire and delete it | Pending |
| P5 | `knowledge` targets | Default: unsupported in this phase and rejected explicitly by the subclass | Pending |
| P6 | Final-evaluation verdict | At least one accepted iteration and a final test score strictly above the test baseline | Confirmed |

## Goals

- Turn the evaluation gateway into a factory class, a base class, and subclasses: a new platform only adds a subclass and a registration, and `HE_EVAL_MODE` in `.env` selects the implementation.
- Add the ai-eval-platform subclass that encapsulates launch, status, results, the error envelope, and the service token.
- Run a real baseline evaluation of the initial version when a run starts, in parallel with the iteration-1 candidate evaluation.
- Keep the verdict in the service layer: accept only when the candidate score is strictly above the baseline, and move the baseline after an acceptance.
- Produce a test-set final evaluation after the last iteration, with the verdict set when at least one iteration was accepted and the final test score is strictly above the test baseline.
- Add a primary metric key for validation and one for test to the target configuration, and carry both project IDs into the evaluation config snapshot when the run is created.
- Inject the options from GitHub Secrets into `.env` through the Deploy pipeline, and sync the docs and `.env.example`.

## Design authority

- [14 §2 Terms and semantics](../../../plans/fullstack-design/14-target-project-ids.md): the validation set drives per-iteration candidate decisions and the test set drives the final independent acceptance; that slice left the evaluation gateway to a follow-up, and this issue is that follow-up.
- [07 §5.7 Evaluation access and polling](../../../plans/fullstack-design/07-backend-implementation.md): the existing gateway seam and the `HE_EVAL_*` fallback; this issue replaces the mode branch with a registry, so the section must be revised together.
- [07 §5.8 Applying evaluation results, retries, and the final evaluation](../../../plans/fullstack-design/07-backend-implementation.md): the existing verdict, retry, and final-evaluation flow; this issue adds the baseline, the gate, and the test-set final evaluation.
- [05 §4.11 Evolution target configuration](../../../plans/fullstack-design/05-api-design.md): the target configuration API; this issue adds one primary metric key each for validation and test.
- [06 §5.2 evolution_runs](../../../plans/fullstack-design/06-database-design.md): the `eval_config` and project ID snapshots; this issue adds run-level evaluation storage.
- [04 §9 Configuration reference](../../../plans/fullstack-design/04-backend-architecture.md): the meaning of `HE_EVAL_*` changes with this issue.
- [Agent Note: real patch and evaluation seams](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/architecture/2026-11-17-real-patch-eval-seams.en.md): records the current mode factory and the Secrets channel decisions; this issue updates its facts.
- External references: [evaluation platform PR #431](https://github.com/Shadow-Azure/ai-eval-platform/pull/431), [evaluation platform issue #429](https://github.com/Shadow-Azure/ai-eval-platform/issues/429), [microsoft/SkillOpt](https://github.com/microsoft/SkillOpt).

## Implementation

### Solution overview

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

Switching platforms only touches the subclass and the registry; the verdict, the moving baseline, and the final evaluation all live in the service layer, and a platform subclass only handles protocol and field mapping.

### Gateway factory

- `third_party_api/eval_gateway/base.py`: `BaseEvalGateway(ABC)` declares `provider`, the frozen config, and `submit`, `get_status`, and `get_result`, and hosts the sanitized HTTP and error handling.
- `third_party_api/eval_gateway/factory.py`: `EvalGatewayFactory` keeps the registry and exposes `register`, `create`, and `registered`; at assembly time it produces a subclass instance from Settings and the run snapshot.
- `FakeEvalGateway` becomes a subclass of the base class and moves into `third_party_api`, with a re-export kept at the old location.
- `gateway_factory.py` looks the implementation up in the registry and keeps the `build_eval_gateway_factory(settings)` signature; the legal `eval_mode` values in `config.py` come from the registry.
- The old `HttpEvalGateway` and `EvalMapper` retire together with the fictional protocol, and the stub tests move to the real contract.

### ai-eval-platform subclass

- Submit: `POST /api/v1/eval-templates/{validationProjectId}/launch` with a Bearer service token; the `Idempotency-Key` combines the run, the iteration number, the candidate commit, and the attempt counter; the body carries commit, ref, asset_paths, and asset_types in `asset_override`, plus `lineage`.
- After submit, assert that `asset.resolved_commit` equals the candidate commit and record `warnings` as run events.
- Status mapping: the platform's 11 states fold into HE's 5 states, and an unknown state fails explicitly.

| Platform state | HE state | Note |
|---|---|---|
| `preparing`, `queued` | `queued` | Waiting |
| `running`, `finalizing`, `cancelling` | `running` | Executing |
| `completed` | `completed` | Fetch results |
| `partial` | `completed` | Subject to the minimum completion guard; below it the evaluation fails |
| `failed`, `cancelled` | `failed` | Terminal failure |
| `pausing_budget`, `paused_budget` | `failed` | The platform does not recover by itself; fail directly with an actionable message |

- Results and errors: the metric items in `results` become the measurement as-is, and the service layer picks the primary metric; the error envelope maps to a gateway error that carries the platform error code, where 401, 403, 404, and 422 are not retryable and 5xx, 429, and network errors are flagged retryable.
- Asset mapping: `skill` uses `asset_paths=[subDir]`; `agent` is declared explicitly as a subagent through `asset_types`; `knowledge` is rejected explicitly.

### Baseline, gate, and test-set final evaluation

- Add a run-level evaluation table that stores evaluations belonging to no iteration: the validation baseline, the test baseline, and the test-set final evaluation; its columns mirror the per-iteration evaluation columns, with the external ID, status, poll time, attempt counter, score, and raw metric items.
- Right after the run is created, submit the validation baseline and the test baseline in parallel; the iteration-1 candidate is submitted as usual, and its verdict waits for the validation baseline to complete.
- Gate: the baseline of iteration N is the candidate score of the most recent accepted iteration, or the validation baseline when none exists; a candidate is accepted only when its score is strictly above the baseline, compared along the validation primary metric key and its direction, and a tie is rejected.
- `EvalGateway.get_result` returns a measurement; the gate component in the service layer produces the `EvalResult` before it is persisted, so `apply`, the final evaluation, and the frontend read the same shape.
- After the last iteration ends, submit the test-set final evaluation and write `evolution_finals`: the initial score is the test baseline, the best score is the final test score, and the verdict requires at least one accepted iteration and a final score strictly above the baseline.
- The `Harness-Decision-Rule` trailer in commit messages and the verdict text change to the real rule.

### Target configuration, snapshot, and contract

- `evolution_targets` gains two columns, `validation_metric_key` and `test_metric_key`, with a migration; the request model, repository, and OpenAPI contract are regenerated.
- When the run is created, `validationProjectId`, `validationMetricKey`, `testProjectId`, `testMetricKey`, and `subDir` are written into the `eval_config` snapshot, and an `eval` passed by the wizard takes precedence.
- When a real platform is selected but the template ID or a primary metric key is missing, creating the run returns 422 and points at the field.
- The target configuration form gains a primary metric key field next to each of the validation and test project IDs, and the list and error messages follow.

### Configuration, deployment, and docs

```text
HE_EVAL_MODE=fake or ai-eval-platform
HE_EVAL_BASE_URL=<platform base URL>
HE_EVAL_API_KEY=<service token; inject via GitHub Secrets only>
```

- `.env.example` updates the descriptions of the three `HE_EVAL_*` keys; the pipeline injection already covers them, so no new Secret is needed.
- `deploy.yml` removes a key explicitly when its Secret is empty, so a deleted Secret no longer leaves a stale value active.
- `docs/architecture.md` drops the "not yet" entry for real evaluation and describes the new seam; `docs/deployment.md` and the deployment playbook follow.
- Agent Notes: update the facts in the real patch and evaluation seams note and add one note recording the baseline gate and the test-set final evaluation.

## Implementation steps

1. Add the migration, model, and repository of the run-level evaluation table, with dual-dialect database tests.
2. Turn `FakeEvalGateway` into a `BaseEvalGateway` subclass, introduce `EvalGatewayFactory`, and keep behavior under the default configuration identical to today.
3. Implement the gate component and the moving baseline, change `get_result` to return a measurement, and run fake mode through the same gate.
4. Implement the ai-eval-platform subclass and a stub of the real contract, covering submit, the status table, results, and the error envelope.
5. Wire the baseline evaluation and the parallel iteration-1 submission, plus the test-set final evaluation after the last iteration.
6. Add a primary metric key for validation and one for test to the target configuration, carry the template ID and both metric keys in the run snapshot, and regenerate the contract.
7. Update `.env.example`, `deploy.yml`, the docs, and Agent Notes, then run every gate.
8. Platform-side operations: the requester creates the validation and test templates in the evaluation platform console, then creates the service token and configures the GitHub Secrets, and acceptance follows with a real run.

## Dependencies and boundary

- Dependencies: m12-03 (the evaluation gateway seam and the `HE_EVAL_*` Secrets channel), already done.
- Platform-side prerequisites (outside this repository's code): validation and test templates with self-evolution reporting off configured by the requester in the evaluation platform console, a service token with both scopes, and `HE_EVAL_MODE`, `HE_EVAL_BASE_URL`, and `HE_EVAL_API_KEY` in GitHub Secrets.
- Boundary: deliver only the HE-side gateway, gate, storage, target configuration, and deployment docs; the evaluation platform's code and templates stay with the platform repository or console.
- Pending items are implemented with their default values from the discussion record; a later decision is adjusted within the same PR.

## Verification

```sh
pnpm test:api -- -k "eval_gateway or gateway_factory or eval_gate or evolution_evaluations"
pnpm test:db
pnpm contract:check
pnpm verify:flow
pnpm lint:docs
```

- Data: a local stub written against the platform's real contract (the launch, status, and results endpoints, 11 states, and the error envelope), plus the bare remote and seed repository already used in tests.
- Expected: after the run starts, the baseline and the iteration-1 candidate have different idempotency keys and are in flight concurrently; a candidate score equal to the baseline is rejected, a higher one is accepted and moves the next baseline; a rejected candidate leaves the run branch unchanged; the final row carries the test baseline and final test scores, and the verdict follows the agreed rule; fake mode produces the same results as today.

## Acceptance

- With `HE_EVAL_MODE=ai-eval-platform` the gateway is the registered subclass and an unknown value fails startup; behavior under `fake` matches today.
- In a real run, the validation baseline and the iteration-1 candidate evaluation are in flight in parallel, and the iteration-1 verdict happens after the baseline completes.
- A candidate is accepted if and only if its score is strictly above the baseline; after an acceptance the next baseline equals the accepted candidate's score, and after a rejection the baseline is unchanged.
- After submit, `asset.resolved_commit` equals the candidate commit; the platform's 4xx configuration errors enter `blocked(stage=eval)` with the platform error code.
- After the run ends, `evolution_finals` records the initial and final scores on the test set, and the verdict requires at least one accepted iteration and a final score strictly above the baseline.
- The target configuration saves the validation and test primary metric keys separately, and creating a run without them returns 422; the contract has no drift.
- Coverage stays at 80% or above, and the flow and document gates pass.

## Gates and CI

- Hit: `pnpm test:api`, `pnpm test:db`, `pnpm test:gates`, `pnpm contract:check`, `pnpm lint:api`, `pnpm typecheck:api`, `pnpm verify:flow`, `pnpm verify:flow-online`, `pnpm lint:docs`, `pnpm verify:docs`.
- Add or update an Agent Note in the same PR; no new gate scripts.

## Non-goals

- Do not change the evaluation platform's code or contract; the requester configures the dedicated templates in the console, and HE never creates them.
- Do not merge automatically; promotion still goes through a human-reviewed PR.
- Do not refine the acceptance rule: a minimum improvement, repeated evaluations, and noise handling are left for later.
- Do not register HE's push fork as a platform asset source, and do not introduce a generic `/evals` protocol.
- Do not write production addresses, tokens, or console credentials into the repository.
