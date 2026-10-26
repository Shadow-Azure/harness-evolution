# Agent Note: Evolution State and Engine Boundaries

Status: implemented

English | [中文](2026-10-27-evolution-state.md)

## Problem

The evolution workflow needs a durable cursor, deterministic placeholder clustering, and replaceable executors. Recomputing six-stage status in every consumer, scattering placeholder policy across API and database code, or masking unsupported stages with empty engine methods would make historical runs unreproducible and let clients disagree about the same stage.

## Decision

`db/crud/evolution.py` exclusively persists runs, clusters, rounds, and finals; conditional updates use the expected `progress_unit` as the concurrency boundary. `service/evolution/state.py` is the sole source for six-stage `done/active/pending`, readability, and one-unit transitions. `service/evolution/cluster.py` exclusively owns fixed type order, split rules, placeholder copy, `TYPE_IMPACT`, and canonical hashing. `EngineFactory` selects `FullEvolutionEngine` or `ClusterOnlyEngine` from the immutable `engine_key` captured when the run is created; engines declare capabilities through `stages()`, undeclared stages and unknown engines fail fast, and cluster-only implements prepare only. The evaluation gateway receives a deeply frozen `eval_config` snapshot rather than reading mutable runtime settings.

## Alternatives considered

Duplicating cursor formulas in the job runner or API would drift; copying clustering policy into the repository would create a second fact source; retaining empty advance/apply/finalize methods on cluster-only would present unsupported behavior as callable; passing a mutable configuration object would let later global changes contaminate historical runs.

## Consequences

Later M5 slices add target APIs, run APIs, concrete stage orchestration, and UI through the same repository, state functions, and engine public surface. New executors register another `engine_key` and declare their stages without changing tables, frontend contracts, or the engine chosen by historical runs. Unknown engines and invalid stages fail explicitly instead of degrading silently.
