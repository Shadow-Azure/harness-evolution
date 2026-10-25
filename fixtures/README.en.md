# Fixture Corpus

English | [中文](README.md)

`fixtures/m2-synthetic/` is deterministic M2 development data. `corpus.json` uses a closed schema for four root sessions plus issue, attribution, and target configuration; `payloads/` contains one JSONL file per transcribed agent. The loader derives hashes and line counts instead of trusting redundant manifest fields.

Run `pnpm fixtures:check` for schema, path, JSONL, and byte-budget validation, then `pnpm fixtures:seed` to write the real SQLite/MySQL tables. Project paths stay under the synthetic `/workspace/` root and repository URLs cannot carry credentials; every JSONL line must match its manifest session, child agents must declare a matching `agentId`, and duplicate JSON keys fail. Seed is limited to demo or test environments and upserts by stable key: unchanged content writes nothing, fixture-owned changes update in place without replacing primary keys, and first-seen timestamps plus normalization state are preserved. It does not commit real Claude sessions, credentials, or derived clusters.
