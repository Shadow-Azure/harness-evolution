# Fixture Corpus

English | [中文](README.md)

`fixtures/m2-synthetic/` is deterministic M2 development data. `corpus.json` uses a closed schema for four root sessions plus issue, attribution, and target configuration; `payloads/` contains one JSONL file per transcribed agent. The loader derives hashes and line counts instead of trusting redundant manifest fields.

`fixtures/attribution-golden/cases.json` is the sanitized attribution-quality baseline. It stores only synthetic titles, ordering, object occurrences, report points, and Agent-relation coordinates—never raw messages, user or repository names, or credentials. It covers self/discovery, non-root-cause presence, multiple occurrences, multiple objects, missing traces, degraded relations, non-Skill problems, and prompt injection. Run `pnpm attribution:evaluate -- --engine agent-skill-stub-v1 --output <file>` to create an isolated comparison report.

Run `pnpm fixtures:check` to validate both corpora for schema, path, JSONL, and budgets, then `pnpm fixtures:seed` to write the M2 SQLite/MySQL tables. Project paths stay under the synthetic `/workspace/` root and repository URLs cannot carry credentials; every JSONL line must match its manifest session, child agents must declare a matching `agentId`, and duplicate JSON keys fail. Seed is limited to demo or test environments and upserts by stable key: unchanged content writes nothing, fixture-owned changes update in place without replacing primary keys, and first-seen timestamps plus normalization state are preserved. It does not commit real Claude sessions, credentials, or derived clusters.
