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

## Alternatives considered

- Treating upstream responses as FastAPI OpenAPI: rejected because outbound lifecycle and error ownership differ, which would pollute generated client routes with non-existent inbound operations.
- Contacting a live upstream in CI: rejected because real integration belongs to M6, and M2 needs deterministic mock transport.
- Creating a second upstream payload table: rejected because each trace needs one raw source of truth for stable idempotency and runtime cursors.

## Consequences

M2 proves only the client contract and mock behavior, not live upstream availability; M6 must validate compatibility against a real implementation.

Runtime adds an `httpx` dependency. Missing upstream configuration returns `UPSTREAM_NOT_AVAILABLE` rather than a partially enabled pull capability.
