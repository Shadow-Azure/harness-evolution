# Agent Note: Attribution Report V2 and Manifest Cache

Status: implemented

English | [中文](2026-11-17-attribution-report-v2.md)

## Problem

The old `probe_reports` boundary had only a definitive binary conclusion, a category, and two text fields, while its cache identity could not represent a Skill, model, context, or output schema. Attaching pluggable Agent Skills to that boundary would reuse results whose semantics had changed and would encode insufficient evidence as a definitive non-target conclusion.

## Decision

`probe_reports` remains the sole report source of truth and gains nullable JSON fields for a `probe-report/v2` structured payload and an immutable `attribution-execution/v1` manifest. New V2 writes use the SHA-256 of canonical manifest JSON as `cache_key`; the manifest covers workspace, Badcase, target revision, policy, engine, Skill revision/content hash, model-configuration fingerprint, context snapshot hash, and output schema. Legacy rows and writes without a manifest retain the seven-part cache key. Conclusions become `attributed|non_target|inconclusive`; insufficient evidence is `inconclusive` and never reaches clustering, while execution failures still block the run without producing a report. The rule engine now uses the immutable Skill revision resolved by the registry and retains `model=none` as its model placeholder, so later context-snapshot and Agent-executor work only replaces the remaining manifest inputs.

Local Skill reports carry an explicit verdict about the selected target. The platform writer copies its identity from the input; the Skill records the causal mechanism or evidence gap, supports its judgment with trace references and can propose improvements for any verdict. A matching identity cannot establish causation. A pending snapshot with an older writer can only yield an inconclusive result with a warning.

## Alternatives considered

A second V2 report table was rejected because it would create two report IDs and a read-precedence rule. Backfilling every legacy row as fake V2 was rejected because it would claim Skill and context evidence that never existed, so nullable legacy compatibility remains. An `attribution_executions` audit table is deferred to the scheduling and observability iteration: the current runner has one synchronous attempt and run-level blocked state, so adding the table now would freeze a retry state machine that is not designed yet.

## Consequences

The read API can return legacy text together with an optional V2 payload and manifest, without disturbing old reports; changes to Skill, model, context, or schema naturally miss the cache. The context hash freezes the redacted Session Agent tree, object occurrences, Badcase report coordinates, evidence paths, knowledge evidence, and historical-report references without storing raw Trace content. The database gains four nullable columns and one ordinary index, with MySQL and SQLite sharing the same JSON contract.
