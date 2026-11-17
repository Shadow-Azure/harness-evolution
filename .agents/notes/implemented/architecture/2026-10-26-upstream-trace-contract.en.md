# Agent Note: Upstream trace query boundary

Status: implemented

English | [中文](2026-10-26-upstream-trace-contract.md)

## Problem

The upstream trace API does not exist yet, while this service still needs stable version, pagination, retry, per-session isolation, and raw-payload persistence semantics without contacting a live service.

## Decision

The upstream contract is an independent outbound contract under `third_party_api/trajectory/`. Strict frozen Pydantic models generate a JSON Schema and fixture; they do not enter FastAPI inbound OpenAPI.

`HttpTrajectorySource` uses an injected `httpx.AsyncClient` and mock transport in tests. `HE_UPSTREAM_API_MAJOR` accepts only `1` and rejects every other major during configuration loading, while each response header is still checked. Retries cover 429, 5xx, timeout, and transport failures up to three times after the initial request; ordinary 4xx and version failures are not retried. The FastAPI lifespan releases resources owned by an injected source.

An administrator pull job maps successful packages to raw JSONL rows in the existing `trajectory_payloads` table, then enters the shared root replay pipeline. Per-session failures become sanitized sync errors without discarding other successes.

Runtime models accept only canonical camelCase aliases and real booleans, rejecting snake_case or string booleans as a second wire contract. The exported JSON Schema enforces exactly one main transcript on the `transcripts` array, a null main-agent id, and a non-null child-agent id. A child reusing the root id is rejected through an Ajv `$data` reference; metadata times use RFC 3339 date-time and an ordered-range extension, while cross-transcript uniqueness remains a runtime check. Upstream provenance is stored as `http_api`. An incompatible major version fails the whole batch instead of degrading to an item issue; session mismatches, 404s, retry exhaustion, and response-decoding failures remain isolated per session.

Productionization (m12-01) adds three things. First, live integration is explicitly opt-in: `tests/m12-01-real-trace-upstream` runs credential injection, cursor pagination, per-session isolation, manual re-pull, and manual replay against a loopback HTTP service; only `-m live_upstream` reaches a real upstream, and the group skips without credentials, keeping CI hermetic. Second, the client and pull job emit structured health and drift logs: `upstream.health` (ok / degraded / failed with request, isolation, write, duration, and bounded error-code fields), `upstream.version_observed`, `upstream.version_drift` (missing, unparseable, incompatible major, or a version change within one process), `upstream.contract_drift` (model name and error count), and `upstream.request_retry` / `upstream.request_failed`; logs carry only bounded enums, counts, and major numbers, never response bodies, session ids, or credentials. Third, manual replay reuses the existing administrator entry points: `POST /api/acquisition/pull` with `sessionIds` re-fetches failed sessions, and `POST /api/acquisition/sync` replays stored pending payloads; an upstream fault only fails the pull job or produces per-session sync errors and never blocks the script path into `trajectory_payloads`.

## Alternatives considered

- Treating upstream responses as FastAPI OpenAPI: rejected because outbound lifecycle and error ownership differ, which would pollute generated client routes with non-existent inbound operations.
- Contacting a live upstream in CI: rejected because live integration requires explicit opt-in credentials, and the default suite uses mock transport plus a loopback service.
- Creating a second upstream payload table: rejected because each trace needs one raw source of truth for stable idempotency and runtime cursors.

## Consequences

In-repo tests prove the client contract, mock behavior, and loopback real-HTTP integration; compatibility with a real external upstream still requires the opt-in suite in a credentialed environment.

Runtime adds an `httpx` dependency. Missing upstream configuration returns `UPSTREAM_NOT_AVAILABLE` rather than a partially enabled pull capability.
