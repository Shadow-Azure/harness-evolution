# Optimize trajectory_payloads storage: compression, object-storage tiering, and re-download boundaries

English | [中文](m29-payload-tiered-storage.md)

```yaml flow
kind: issue
id: m29-01
milestone: m29
depends: []
priority: P1
status: ready
scope:
  - apps/api/app/db/**
  - apps/api/app/service/acquisition/**
  - apps/api/app/service/evolution/**
  - apps/api/app/config.py
  - apps/api/alembic/versions/**
  - apps/api/tests/**
  - deploy/**
  - docs/**
  - .env.example
  - .agents/**
  - plans/**
  - scripts/**
adr: []
github:
  number: 654
  url: https://github.com/Shadow-Azure/harness-evolution/issues/654
```

## Background

### Current state

`trajectory_payloads.payload` is `LONGTEXT`, one row per agent (the main agent or a subagent), and holds that agent's full raw JSONL; the same row's `content_hash` is the SHA-256 of the payload, and `source_type` records the `script` / `http_api` ingest channel. The design facts are in [06 §3.0](../../../plans/fullstack-design/06-database-design.md) and [06 §6](../../../plans/fullstack-design/06-database-design.md), and the table is defined by `trajectory_payloads` in `apps/api/app/db/models/domain.py`.

Production is a single Alibaba Cloud ECS instance: nginx, uvicorn, and MySQL 8 on one host with a 40GB system disk; see the [deployment docs](https://github.com/Shadow-Azure/harness-evolution/blob/main/docs/deployment.en.md) and the [Aliyun playbook](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/deploy-aliyun-playbook.md). The estimated scale is 10³–10⁴ rows ([06 §6](../../../plans/fullstack-design/06-database-design.md)); the repository's prototype sample covers 4 real root session families, 64 rollouts, 25,170 records, and about 72.2MB ([Session family prototype note](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/proposed/architecture/2026-10-19-session-family-prototype.en.md)), or about 1.1MB per row, which extrapolates to roughly 1–11GB of raw text at 10³–10⁴ rows. This is the largest table, and it has no retention or delete path.

There are only two read paths: normalization replay reads payloads that meet the pending condition (`list_pending_payloads`), and local attribution plus per-root replay read every payload of one root (`list_root_payloads`). Normalized business tables do not keep messages or content blocks; when the raw text is needed it is read back by `(runtime_key, root_session_id, agent_id)`. After normalization, payloads are effectively cold data, but a parser upgrade triggers replay again. The code lives in `apps/api/app/db/crud/acquisition_replay.py`, `apps/api/app/service/acquisition/replay.py`, and `apps/api/app/service/evolution/local_attribution.py`.

There are three write paths: third-party script upsert (`script`), upstream pull (`http_api`), and bad-case root-session sync (`http_api`). There is no payload deletion job today; when a payload is missing, normalization keeps the business data and records a log entry (`list_missing_payload_sources`). That is the compatibility seam a tiered design can reuse when an object is missing.

### Request

- Reduce the MySQL space used by `trajectory_payloads`, so the primary database does not grow without bound with historical sessions.
- Evaluate "store only a download reference and re-download low-frequency payloads later", not just in-database compression.
- Look at mature solutions and high-star open-source projects, and state the recommendation, costs, risks, and sources.
- Put the option selection in this issue for discussion first; implementation starts only after the choice, and this issue does not change code.

## Goals

- Remove payloads from primary-database hot data without losing raw evidence or changing normalization and replay semantics: compress first, then tier low-frequency payloads to object storage.
- `trajectory_payloads` remains the single source of truth for raw traces; reads by `(runtime_key, root_session_id, agent_id)`, idempotent replay by `content_hash`, and replay after a parser-version upgrade keep their semantics.
- Keep one logical copy of each payload (either the primary database or object storage), not a long-term double write of "one in the database, one in object storage".
- Upstream re-download is only an optional recovery path when an object is missing, never the sole copy; `script` sources must not depend on it.
- Define measurable acceptance for capacity, read latency, failure handling, and rollback; the numbers are set after a read-only measurement.

## Design authority

- [06 §3.0 `trajectory_payloads`](../../../plans/fullstack-design/06-database-design.md): payload column, primary key, `content_hash`, `source_type`, and the "this service only reads" boundary.
- [06 §6 Index and capacity estimates](../../../plans/fullstack-design/06-database-design.md): `trajectory_payloads` is 10³–10⁴ rows and payloads dominate its size.
- [01 §6 Deployment shape and scaling path](../../../plans/fullstack-design/01-architecture.md): MySQL runs on the same single host, with no separate object-storage layer.
- [07 §2 Raw trace ingest and normalization](../../../plans/fullstack-design/07-backend-implementation.md): pending condition, pull writing payloads, and root-atomic replay.
- Current code: `trajectory_payloads` in `apps/api/app/db/models/domain.py`; `list_pending_payloads` / `list_root_payloads` in `apps/api/app/db/crud/acquisition_replay.py`; the re-download entry `fetch(session_id)` in `apps/api/app/third_party_api/trajectory/http.py`.
- Capacity sample: 64 rollouts / 72.2MB in the [Session family prototype note](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/proposed/architecture/2026-10-19-session-family-prototype.en.md).

## Option comparison

| Option | Primary-DB reduction | Keeps raw text and replay | Main cost and risk | Verdict |
|---|---|---|---|---|
| A. Application-level zstd compression | About 3–5x, to be measured | Yes | Migration and backfill; compression/decompression CPU; still grows linearly | Do first |
| B. Object-storage tiering (claim check) | Primary DB keeps only metadata and a hot window, about 90%+ | Yes | New OSS dependency, network read latency, object lifecycle and backup/restore | Recommended second phase |
| C. Reference-only, re-download on demand | Close to 100% | Only `http_api`, and only while upstream is available | `script` cannot re-download; upstream retention, availability, and immutability are not guaranteed; batch replay becomes many network calls | Not the main design; recovery only |
| D. MySQL native page compression | Usually lower than A | Yes | MySQL 8.0 only supports page-level Zlib/LZ4, needs sparse files and hole punching, applies to the whole table and indexes, little tuning room | Not the main design |
| E. Separate archive database or cold table | Partial | Yes | Another database to operate; no cost advantage over object storage; more complex query path | Not recommended |

### Option A. Application-level compression

Store the payload compressed with zstd in the same logical column, with codec and byte-count metadata; compress on write, decompress on read, and keep `content_hash` over the raw text. The change is local, works the same on SQLite and MySQL, and reuses the same encoding later for object storage; the costs are a historical backfill and compression/decompression CPU. zstd dictionaries and long windows suit JSONL with highly repeated keys, but the actual ratio must be measured on production data; the ratio must not be treated as an acceptance premise.

### Option B. Object-storage tiering

Use the claim check pattern: upload the payload object to object storage and keep only identity, hash, codec, byte count, and the object key in `trajectory_payloads`; reads fetch the object, verify the hash, and decompress. The primary database stops carrying historical payload volume, which also reduces `mysqldump`, DDL, and disk pressure. The cost is a new durable dependency: private bucket, lifecycle, versioning/backup, and missing/corrupt error reporting; read latency changes from a local row read to an object GET, so a cache or hot window is needed.

### Option C. Reference-only re-download

This is the direction first raised: keep no payload, only `(runtime_key, root_session_id, agent_id)` and the upstream address, and download on low-frequency access. It only works for `http_api` rows; `script` rows are written directly by third-party scripts and have no upstream to call. Even for `http_api`, the upstream contract is a client contract defined by this service, not a long-term archive promise from upstream; retention, availability, and immutability are not under this service's control. A parser upgrade triggers a batch replay and turns one database scan into many HTTP requests, with 404/410, 429, timeout, and content-drift failures. It fits "recover a missing object", not "the only copy".

### Option D. MySQL native page compression

MySQL 8.0 `COMPRESSION` is InnoDB page-level compression supporting Zlib/LZ4, requires sparse file and hole-punching support, and applies to whole tables and indexes; it is not column-level compression and cannot target only `payload`. It can reduce disk use, but the ratio, filesystem support, and buffer-pool impact are not controllable, and it does not compose with object-storage tiering. It can be evaluated as a stopgap, not as the recommended main design.

### Option E. Separate archive database or cold table

Moving historical payloads to another database or a cold table relieves the primary database, but does not fix the root cause: large text does not belong in a transactional database. It adds backup, monitoring, and restore cost, usually above object storage. Unless an archive platform already exists, it is not recommended.

## Implementation

The recommendation is A → B in two phases; C is only an optional recovery path for B; D/E are not adopted. The following is the design for the recommended option. After the choice is confirmed, move this issue to in-progress and split implementation.

### Phase 1: payload compression

- Add `payload_codec` (`raw` / `zstd`) and `payload_bytes` (raw byte count) to `trajectory_payloads`; change `payload` to a binary column (MySQL `LONGBLOB`, SQLite BLOB); new writes default to zstd, and reads decompress by codec. `content_hash` is still computed over the decompressed raw text, so replay and idempotency do not change.
- Backfill historical rows in batches: select by primary-key range, compress, write back, and record progress; a failed batch is retryable and already-compressed rows are skipped by codec. If the production `ALTER TABLE` lock or rebuild time is unacceptable, use a shadow `payload_zstd` column plus dual reads, and drop the old column in a later release after the backfill.
- Start at zstd level 3 and adjust from measured CPU and ratio; do not compress at a high level on the request path; the backfill job can run slower.
- Route all reads through one `decode_payload(row)` helper so callers do not each implement codec checks; old `raw` rows stay readable so the new and old versions can coexist during a rolling release.

### Phase 2: object-storage tiering

- Add nullable `payload_object_key` and allow `payload` to be empty; a row must have exactly one of "database payload" or "object key". Use content-addressed keys: `payloads/{runtime_key}/{root_session_id}/{agent_id}/{content_hash}.jsonl.zst`; repeated uploads of the same content are idempotent and easy to verify and clean up.
- An offline job selects rows with `updated_at < now - HE_PAYLOAD_OFFLOAD_AFTER_DAYS`, already normalized (`source_records.processed_hash = content_hash`), and a non-empty `payload`; it uploads and verifies the object, then writes `payload_object_key` and clears `payload` in one transaction. If the upload succeeds but the transaction fails, only an orphan object remains, cleaned by the lifecycle rule; there is never "deleted from the database, object missing".
- Read path: if the database payload exists, decompress it; if only an object key exists, GET the object, verify `content_hash`, and decompress; a missing object or hash mismatch returns a stable failure diagnosis and never treats empty content as a valid payload. Replay still isolates per root, so one root's object failure does not fail the batch.
- Batch replay must not pull every pending payload into memory at once: page identities by root or runtime, bound concurrent object GETs, and read and normalize one root at a time; a full replay after a parser upgrade obeys the same bound.
- Prefer Alibaba Cloud OSS for object storage (S3-compatible, same region as ECS, private bucket, server-side encryption, versioning, and lifecycle); development and tests use a local filesystem implementation of the same `PayloadObjectStore` interface, and CI does not touch the cloud. Inject `HE_PAYLOAD_OBJECT_*` through the environment; credentials live only in environment variables, never in the repository or logs.
- Backup and restore: primary-database dumps no longer contain payloads, so object-storage versioning/lifecycle and restore steps must be documented, with a restore command by `(runtime_key, root_session_id, agent_id)` or object prefix.

### Boundaries for re-download

- Only rows with `source_type = http_api` have a re-download entry (`HttpTrajectorySource.fetch(session_id)`); `script` rows have no upstream address and must keep a durable copy in object storage.
- Accept a re-download only when upstream explicitly retains the session and the returned content's `content_hash` matches the row; a mismatch means the content changed, must not silently overwrite the existing normalized result, and should be diagnosed and decided through replay or manual review.
- Re-download must handle 404/410, 429, timeouts, upstream version drift, and the request volume of a batch replay; it fits single-session recovery, not a full replay after a parser upgrade.
- If OSS cost becomes the main constraint later and upstream gives a retention guarantee, a "delete objects after N days, re-download on demand" policy can be added as an optional phase 3, off by default, keeping the hash and failure diagnosis.

## Implementation steps

1. Measure production with read-only queries: row count, `SUM(LENGTH(payload))`, p50/p95 payload size, and distribution by runtime/source_type/updated_at; measure the zstd ratio on a sanitized sample and keep payload content out of the repository and issue.
2. Set the phase-1 compression target, backfill batch size, and `ALTER TABLE` approach from the measurement; confirm the object-storage region, bucket, private ACL, encryption, lifecycle, and backup owner.
3. Implement phase 1: schema migration, codec, batch backfill, dual reads, and the decode helper; add unit/integration tests proving both old `raw` and new zstd rows replay.
4. Implement phase 2: object-storage interface and local implementation, upload/verify/offload job, read fallback, missing and hash-mismatch error reporting, and the restore command; add fake-object-store tests.
5. In staging, run normalization, replay, attribution, and restore with fixtures and one sanitized real sample; record primary-database bytes, object GET latency, and failure rate; then roll out behind a switch.
6. After one retention cycle, decide whether to enable phase-3 "delete objects, re-download on demand"; do not enable it without an upstream retention guarantee.

## Dependencies and boundary

- Code dependencies: none. Phase 1 can ship independently; phase 2 needs an object-storage bucket, region, and credentials as deployment prerequisites.
- Delivery boundary: change only payload storage, reads, and migration; do not change normalization rules, business-table structure, existing API semantics, or the upstream trace contract; do not add a second logical copy; do not delete historical payloads without a durable copy.
- Phase 1 and phase 2 can be separate issues/PRs; this issue first completes selection and design, then splits implementation, so "discussion" and "implementation" do not share one PR.
- Open decisions: in-place column type change versus shadow column; OSS versus self-hosted MinIO (MinIO on the same 40GB disk does not solve the disk problem, so OSS is preferred); hot window and retention days; whether to keep a plaintext copy for audit (prefer no, rely on hash verification and decoding).

## Verification

This issue defines the acceptance approach and does not claim an implementation or tests that do not exist. The implementation PR must add and run:

```sh
pnpm verify:flow
pnpm lint:docs
pnpm verify:docs
pnpm lint:api
pnpm typecheck:api
pnpm test:api
pnpm test:db:mysql
pnpm test:gates
```

- Phase 1: codec encode/decode tests cover `raw` and `zstd`; migration tests cover SQLite and MySQL; replaying the same fixture before and after the change yields identical business-table rows and fields; a SQL assertion shows zero rows with both `payload IS NULL` and `payload_object_key IS NULL`.
- Phase 2: the fake object store covers upload, read, missing object, and hash mismatch; offload uploads then clears, and repeated runs are idempotent; a simulated "upload succeeds, transaction fails" retry loses no data; per-root replay affects only that root when an object fails.
- Capacity verification: record `SUM(LENGTH(payload))`, total table size, and object-storage volume before and after; compare compression ratio and p95 read latency on the same sample. Concrete thresholds are written into this issue after measurement, not fixed in advance.

## Acceptance

- Phase 1: on a representative sample, primary-database payload bytes drop by at least 60% versus raw text (the final threshold follows the measurement); historical `raw` rows and new `zstd` rows are readable by the same replay path; normalized results match the pre-change baseline; old and new versions coexist during a rolling release.
- Phase 2: payloads older than the hot window and already normalized are no longer stored in the primary database; primary-database growth decouples from historical session count; object reads, hash verification, missing-object error reporting, and the restore command all have tests; an upload/transaction interruption loses no data.
- Operations: object-storage backup/restore, lifecycle, monitoring, and alerts are documented; primary-database dump and restore are updated; failure rate and read latency are observable.
- Selection: this issue records the final choice, rejected options, and reasons; after confirmation, move the status to in-progress and split implementation into independently acceptable issues/PRs.

## Gates and CI

- Flow-file changes in this issue: `pnpm verify:flow`, `pnpm lint:docs`, `pnpm verify:docs`.
- Implementation PR: `pnpm lint:api`, `pnpm typecheck:api`, `pnpm test:api`, `pnpm test:db:mysql`, `pnpm test:gates`; no OpenAPI change is expected, and `pnpm contract:check` runs if an endpoint changes.
- The MySQL lane is mandatory: SQLite-only tests do not cover `LONGTEXT`/`LONGBLOB`, page compression, or migration behavior.
- This change does not touch the UI, so Before/After screenshots are not required; if an evidence-view UI follows, apply the UI rules then.

## Non-goals

- Do not use "store only a download reference, keep no local copy" as the main design; do not make upstream re-download the only storage.
- Do not delete historical payloads without a durable copy; do not lose raw evidence or replay ability to save space.
- Do not change normalization algorithms, business-table structure, existing API semantics, or the upstream trace contract.
- Do not make unrelated UI, product, or database-engine changes.
- Do not make MySQL page compression or a separate archive database the preferred design; do not write implementation code in this issue.

## References

The projects and documents below show mature ways to move large payloads out of a transactional database, tier hot and cold data, and fetch by reference. Star counts are approximate values read from the GitHub API on 2026-11-27.

- [Temporal External Storage](https://docs.temporal.io/external-storage): claim check, payloads above a threshold go to S3 and similar stores while workflows pass only a reference; covers thresholds, parallel upload/download, and reference display in the UI. About 24.6k stars.
- [Azure Architecture Center: Claim Check pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/claim-check): keep the large payload in an external store and send only a reference; lists lifecycle ownership, availability and durability, retrieval latency, write/reference consistency, and integrity checks, which map directly to this issue's risk list.
- [Langfuse Architecture](https://langfuse.com/handbook/product-engineering/architecture): Postgres for transactional data, ClickHouse for traces/observations, S3/Blob for events and attachments; a similar split of analytics store and object storage. About 37.9k stars.
- [Grafana Tempo: Object storage](https://grafana.com/docs/tempo/latest/reference-tempo-architecture/object-storage/): all trace data lives long-term in object storage (S3/GCS/Azure), with local filesystem only for development and tests; demonstrates object storage as the long-term trace backend, including cost and read paths. About 5.6k stars.
- [Apache Kafka Tiered Storage (KIP-405)](https://cwiki.apache.org/confluence/display/KAFKA/KIP-405%3A+Kafka+Tiered+Storage): a local tier keeps recent data and a remote tier holds older data in S3 and similar stores, with retention split by tier; a direct reference for "hot window plus cold objects". About 34.4k stars.
- [MinIO](https://github.com/minio/minio): a high-star S3-compatible object store for self-hosting or local verification; running it on the same 40GB system disk does not solve the disk problem, so production prefers same-region OSS. About 61.2k stars.
- [facebook/zstd](https://github.com/facebook/zstd): a general-purpose compression algorithm with a high ratio and fast decompression, suitable for JSONL text; the encoding basis for phase 1. About 28.3k stars.
- [MySQL 8.0 InnoDB Page Compression](https://dev.mysql.com/doc/refman/8.0/en/innodb-page-compression.html): the official description of MySQL native page-level compression (Zlib/LZ4), used to bound option D.
- [Alibaba Cloud OSS](https://www.aliyun.com/product/oss): the same-region object-storage option in production, with private buckets, server-side encryption, versioning, and lifecycle; the actual bucket and cost follow the deployment environment.
