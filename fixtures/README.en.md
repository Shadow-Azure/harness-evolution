# Fixture Corpus

English | [中文](README.md)

`fixtures/m2-synthetic/` is deterministic M2 development data. `corpus.json` uses a closed schema for four root sessions plus issue, attribution, and target configuration; `payloads/` contains one JSONL file per transcribed agent. The loader derives hashes and line counts instead of trusting redundant manifest fields.

Run `pnpm fixtures:check` for schema, path, JSONL, and byte-budget validation, then `pnpm fixtures:seed` to write the real SQLite/MySQL tables. Seed is limited to demo or test environments and upserts by stable key: unchanged content writes nothing, while changed fields update in place without replacing primary keys. It does not commit real Claude sessions, credentials, or derived clusters.
