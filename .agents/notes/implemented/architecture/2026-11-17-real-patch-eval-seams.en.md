# Agent Note: Pluggable real patch and evaluation seams

Status: implemented

English | [中文](2026-11-17-real-patch-eval-seams.md)

## Problem

Patch generation and evaluation inside the evolution loop were placeholder facts (a placeholder markdown file, FakeEvalGateway placeholder scores). The loop really writes, pushes, and decides, but the artifact is not a real fix and the scores are not real platform verdicts — the "placeholder mistaken for a real conclusion" risk (09 R11). Neither seam had an extension point: changing the generation strategy or adopting a real evaluation platform meant touching business code.

## Decision

Patch generation now lives behind the `PatchSource` seam in `service/evolution/patch_source.py`: factory + Protocol + subclasses. The placeholder source keeps the V1 behavior and labeling; the new `MinimalConfigPatchSource` deterministically maps bad-case evidence text to one config parameter (timeout/retry/index check/permission check) merged into the target repository's `config/<target>.json`, written for real via `Patch.overwrite` semantics and committed into the candidate. The written keys and values are harness-side conventions, not the target repository's config schema — whether a real target accepts them is decided by the evaluation platform's measured verdict, not here; the keyword table's order is the priority, and externalizing the table into configuration waits for a real platform integration. Selection prefers the run snapshot `eval_config["patchMode"]` over the `HE_PATCH_SOURCE_MODE` fallback; an explicit unknown mode raises `ConfigError` instead of silently degrading. The「改动」message section is supplied by the source (persisted as `note` in the turn's `patch` column), so acceptance message rebuilds keep the real description.

Evaluation access is now a mode-driven factory, `build_eval_gateway_factory(settings)`: the run snapshot `eval_config["mode"]` wins over the `HE_EVAL_MODE`/`HE_EVAL_BASE_URL`/`HE_EVAL_API_KEY` fallback; fake stays the default. `HttpEvalGateway` + `EvalMapper` (third_party_api/eval_gateway) own the external field names; `apiKeyRef` stores an environment-variable name and the secret is resolved indirectly from env at call time. A missing baseUrl or a dangling apiKeyRef raises `EvalGatewayConfigError`, absorbed by the existing `blocked(stage=eval)` path with identical semantics on all three routes (first submission, polling, and retry resubmission), without a new event type. The creation-time snapshot stores the `apiKeyRef` name only, exempt from credential redaction (the key is not a secret; a blank reference drops the key entirely), and the run-detail iteration step carries the patch `note`. Transient failures of the polling request itself (network timeouts, connection failures, HTTP 429/5xx) are flagged `retryable` by the gateway layer; the polling loop consumes only that boolean and defers `next_poll_at`, still capped by the existing 2h `eval_timeout` fallback — 4xx-style semantic errors remain final evaluation failures that block.

The user-mandated production channel: `HE_EVAL_*` reaches the server `/opt/harness/shared/.env` via GitHub Secrets in the `Deploy` pipeline (the step skips when secrets are absent); issue #244 scope accordingly adds `deploy/**` and `.github/workflows/**`. Secrets never enter the repository or the database.

## Alternatives considered

Real LLM-generated code fixes: outside the "minimal config change" boundary and not deterministically acceptable; kept as a future patch source subclass. Storing the raw secret in the run snapshot: `eval_config` is persisted and read by events/logs, so the snapshot carries `apiKeyRef` instead. Falling back to fake when the gateway is misconfigured: it would disguise a configuration error as a placeholder verdict, violating R11. Failing the deploy pipeline when secrets are absent: it would block existing releases and contradict the opt-in semantics.

## Consequences

Changing the generation strategy = one new `PatchSource` subclass plus one line of `.env`/run config; adopting a real evaluation platform = one gateway subclass (or HttpEvalGateway aligned to the platform fields) plus `.env` config, with business code untouched. Persisting the final evaluation (`write_final`) advances the run cursor to `5+M+1` in the same transaction, so the final step of a completed run becomes readable; a retry re-entry only updates the final row. The real closed loop (real git push, real HTTP evaluation, real decision) is pinned in `tests/m12-03-real-patch-eval/test_real_loop_evidence.py` against a local bare remote and is repeatable. Under default configuration behavior is identical to m5-10; `docs/deployment.md` budget 740→800 covers the new「评测配置注入」section (still needed after layering-out and compression; rationale in the PR description).
