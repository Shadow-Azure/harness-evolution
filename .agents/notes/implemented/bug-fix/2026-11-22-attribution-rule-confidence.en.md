# Agent Note: Attribution confidence becomes an evidence-completeness rule score

Status: implemented

English | [中文](2026-11-22-attribution-rule-confidence.md)

## Problem

The case-level confidence written by attribution is three constants in the engine (0.8 for a self report, 0.6 for a discovery after object entry, 0.7 for a non-target). They do not represent evidence strength: the same evidence does score the same, but the number is unrelated to how much direct evidence supports the conclusion, step 4 cannot explain it, and a later low-confidence gate has nothing to build on. [#491](https://github.com/Shadow-Azure/harness-evolution/issues/491) and design [07 §5.5.2](../../../../plans/fullstack-design/07-backend-implementation.md) keep model confidence out of case-level attribution and replace it with a rule-decidable completeness score; model scoring stays at the cluster level after clustering.

## Decision

- Count three signals: order comparable (`order=comparable`), failure signature match (the object identity the bad case declares equals the attributed object), and direct version proof (the version or revision the bad case declares hits the revision identity the run resolved, or its bare body hash).
- Bands: three votes 0.9; two votes 0.8; one vote 0.5; zero votes 0.3; direct version proof with a different object identity is contradictory evidence at 0.2.
- A non-target conclusion takes the complement of attribution completeness: the stronger the attribution evidence, the less certain "this is not the object" becomes. An order-unknown case that names both the object and the exact version therefore scores 0.2, while a case with no signal scores 0.7.
- Signals only use persisted data that a retry can reconstruct: `order_state` from the candidate snapshot, object identity and version from the `bad_cases` row, and target identity and revision from the run. No schema column, cache key, or API field changes, and the engine stays `rule-v1`.
- Version proof only accepts the resolved revision (`tag:` / `digest:` / `provider:`), never the run's selected version: the selected version is not part of the cache key, so including it would let one cache key produce different scores and still share the cached row.
- The optional "low-confidence stays out of clusters" gate ships as two constants (switch `False`, threshold 0.5) and is not wired in this issue; enabling it also needs the cluster-input query change.

## Alternatives considered

- **Per-case model confidence**: a natural fit for the attribution cache, but one blind per-case judgement loses cross-case corroboration and costs O(N); #487 rejected it and leaves cluster-level scoring to bugfix-19.
- **Use the matcher's session-level version match as version proof**: session association already requires that match, so the signal would be constantly true and could not distinguish cases. Prepare retries also do not re-run the matcher, they only reload candidates and evidence, so the score would stop being reproducible from the same evidence.
- **Use historical cases' failures as the object's known failure signatures**: that needs a new cross-case query and a new persisted surface, beyond this issue's boundary of changing only the confidence produced by the attribution write path. The signature starts as the object identity the bad case declares; a more detailed error fingerprint can extend the same signal function later.
- **Keep a fixed 0.7 for non-target**: it conflicts with "confidence means confidence in the conclusion" and is equally unexplained; the complement makes the semantics consistent.

## Consequences

- New step-4 attribution rows move from constants to rule values between 0.1 and 0.9; historical cached rows keep their old value and are not backfilled (the cache key is unchanged).
- The failure signature is an object identity, not an error-text fingerprint; a cross-object case that carries the same version lands in the contradictory band (0.2). That conservative choice is intentional.
- The low-confidence gate remains an off switch with no consumer today; it is a reserved design slot, not a defect of this issue.
- The unit matrix pins 0/1/2/3 votes and the contradictory signal; the engine and the runner each have one integration assertion.
