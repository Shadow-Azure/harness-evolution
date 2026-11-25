# Agent Note: SkillOpt-style baseline gate and test-set final

Status: implemented

English | [中文](2026-11-25-baseline-gate-test-final.md)

## Problem

The real evaluation platform supplies measurements and metric directions, not an accept/reject verdict. HE previously trusted the gateway's `externalVerdict` for every turn, and its final evaluation only rolled per-turn validation scores into `init_score` and `best_score`. There was no "evaluate the initial version once as the baseline" and no independent held-out test-set acceptance. Under score noise a candidate could be accepted, and the final conclusion could not answer whether the final version is better than the initial one.

## Decision

Gateway `get_result` returns only an `EvalMeasurement` (primary metric value, metric direction and raw items). The decision lives in the service layer at `service/evolution/eval_gate.py`: turn N's baseline is the latest accepted turn's candidate score, or the run-level `validation_baseline` score when no turn has been accepted; a candidate is accepted only when it is strictly better than the baseline under the metric direction, and ties reject. Acceptance naturally advances the baseline to that turn's candidate score; rejection leaves both the run branch and the baseline untouched.

Run-level evaluations live in the new `evolution_evaluations` table with `kind` values `validation_baseline`, `test_baseline` and `test_final`, mirroring the turn evaluation columns. `evolution_advance` submits the validation and test baselines before publishing turn 1, so they are concurrently in flight with turn 1's candidate evaluation; `evolution_apply` returns "not applied" until the validation baseline completes and the poller re-enqueues it, never deciding early. After the last iteration terminates, `evolution_finalize` submits the test-set final and only writes `evolution_finals` once it completes: `init_score` is the test-baseline score, `best_score` the test-final score, and `verdict` requires an accepted turn and a test-final score strictly better than the test baseline.

Platform errors distinguish retryability: 401/403/404/422 are final and enter `blocked(stage=eval)` with the platform error code; 5xx, 429 and network errors are retryable, so the poller only defers the next poll, still capped by the 2h timeout. A failed baseline or test final also takes `blocked(stage=eval)`; `/retry` clears the failed row and resubmits without rerunning accepted iterations.

## Alternatives considered

Keep the platform verdict: the platform contract does not provide one, and it would re-couple acceptance rules into every platform subclass. Store baselines on `evolution_rounds`: baselines and the final belong to no turn, and reusing the turn table would break the `(run_id, seq)` uniqueness and turn lifecycle. Decide as soon as the candidate result lands: an incomplete baseline would force a guessed score, treating observation timing as a conclusion. Enable baselines and final only on the real platform: fake mode would then take a different decision path from production and tests could not cover the real gate. Compute the test-set final from per-turn validation scores: it cannot answer the held-out test-set acceptance question.

## Consequences

`evolution_finals.best_score` changes meaning from "highest per-turn validation score" to "test-set final score"; frontend fields stay the same but the value's semantics change, a direct consequence of the SkillOpt comparison. Run-level evaluation needs migration `0033` and dual-dialect repository coverage; an old run submits baselines on its first advance or finalize after deployment, and already completed turns are unaffected. The platform `partial` status is completed or failed against a 50% minimum-completion guard, and `paused_budget` fails immediately with actionable information. The per-turn idempotency key includes the attempt count, so a retry after a platform-side failure cannot replay the same evaluation.
