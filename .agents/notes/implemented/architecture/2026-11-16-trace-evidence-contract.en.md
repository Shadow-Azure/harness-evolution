# Agent Note: Trace evidence fields and execution-closure contract

Status: implemented

English | [中文](2026-11-16-trace-evidence-contract.md)

## Problem

M9-06 made parsers and runtime identity independent, but the session tree still only had parse-health `status` and linked/unlinked relations. It could not express an open parent tool call, a child Agent without a final report, or an external attempt failure, and it had no fields for object revisions, Agent/Skill definition fingerprints, or file-read evidence. If those states keep squeezing into `status` or free text, the frontend, attribution, and later runs would mistake "parsed successfully" for "executed to completion".

## Decision

- Add migration `0016` and extend three trace tables in place according to [06 §3.3–§3.4](../../../../plans/fullstack-design/06-database-design.md): `session_families.execution_outcome/end_reason`, `agents.execution_outcome/end_reason/agent_definition_hash/definition_source`, and `agent_events.object_revision/definition_hash/file_read_hash/read_complete/relation_confidence`.
- `execution_outcome` is a non-null closed state `completed / interrupted / failed / legacy_unknown`; adding the column with a NOT NULL default covers legacy rows. `end_reason`, relation confidence, definition/file hashes, and `read_complete` are nullable and stay NULL. The migration guards each column by presence so a MySQL retry after partial DDL adds only what is missing, rejects an existing column with different nullability, supports SQLite and MySQL, and leaves `runtime_key` and `parser_version` untouched.
- `session_families.status` continues to express parse health only; execution closure is carried independently by `execution_outcome`, and neither field overwrites the other.
- The API contract follows: session list items and the tree root return `runtimeKey`, list items return `executionOutcome`, Agent nodes return `executionOutcome/endReason`, Agent evidence returns `agentDefinitionHash/definitionSource`, and events optionally return `objectRevision/definitionHash/fileReadHash/readComplete/relationConfidence`. State fields use closed `Literal` types, and optional evidence is omitted through `exclude_if` when absent.
- `runtime_version` remains `session_families.cli_version`, `parser_version` remains per-runtime on `source_records`, and model evidence remains split between `agents.model` (reported) and `agents.requested_model` (request alias); no duplicate columns are introduced.
- File-read evidence is limited to `file_read_hash` and `read_complete` here; path and range stay parser evidence for M9-02, and knowledge-document `source_path` belongs to M9-05, so 0016 does not invent columns for them.
- [05 §3.1–§3.2](../../../../plans/fullstack-design/05-api-design.md) records these DTO fields and closed sets so the contract does not live only in code.
- This issue only establishes the data and DTO contract. It does not parse new evidence, so every new field stays `legacy_unknown` or NULL until normalization writes it.

## Alternatives considered

- **Create a separate evidence table**: these fields map one-to-one to Session/Agent/event rows; splitting them adds joins and consistency windows without a benefit. Rejected.
- **Reuse `session_families.status` for execution closure**: parse health and execution completion are independent failure axes; merging them loses the "files parse but a child Agent never returned" state. Rejected.
- **Add duplicate `runtime_version` and `reported_model` columns**: `cli_version` and `model` already carry the runtime version and actual model; duplicates create two sources of truth. Rejected.
- **Add database CHECK constraints for every enum**: SQLite needs table rebuilds and MySQL versions differ; validating at the API boundary buys more. The migration stays repeatable instead.
- **Always serialize evidence as null**: the frontend contract asks for "only when present"; Pydantic `exclude_if` keeps responses tight. Rejected.

## Consequences

- Until M9-02 writes real evidence, every Session/Agent is `legacy_unknown`; clients must read that as "unknown", not "completed".
- `relationConfidence` and the file-read fields have no writer yet; M9-02/M9-03/M9-04 will fill them. This issue only guarantees the columns and DTOs exist.
- Adding `runtimeKey` and `executionOutcome` is a breaking OpenAPI addition; in-repo web fixtures are updated, and external clients must adapt before upgrading.
- `object_revision` stays a string carrying `tag:` / `digest:` / `unknown`; M9-04 owns parsing and validation, and this issue does not infer versions early.
- The migration only appends columns and does not change existing keys, runtime identity, or attribution tables; downgrade drops these columns and keeps the other data.
