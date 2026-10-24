# Development flow

English | [中文](README.md)

> Contract home: roadmap → milestone → issue → ADR format, state machine, and gates. Mechanical checks live in `verify:flow`, `verify:flow --diff`, and `verify:flow-online`.

## Hierarchy

| Layer | Files | Responsibility |
|---|---|---|
| Roadmap | `roadmap.md` | Vision, ordered milestones, delivery rules |
| Milestone | `milestones/<id>-*.md` | Stage goals, scope, acceptance, non-goals |
| Issue | `issues/<milestone-id>-*.md` | Independently verifiable work unit |
| ADR | `../notes/` | Decision records linked from issues |

## Machine-readable yaml flow fence

Every file has exactly one yaml flow fence with byte-identical fences on both languages. Roadmaps record `kind` and `milestones`; milestones record `kind/id/title/status/github`. Issues record:

```text
kind: issue
id: m2-03
milestone: m2
depends: [m2-01, m2-02]
priority: P0
status: backlog
scope: [允许修改的 glob]
adr: [相对 Agent Note 路径]
github: {number, url}
```

`id` is the stable local planning ID; `github.number` is the remote ID. Dependencies must exist, stay in the same or an earlier milestone, and remain acyclic.

## Issue body contract

Chinese bodies require Background, Goals, Design authority, Implementation, Implementation steps, Dependencies and boundary, Verification, Acceptance, Gates and CI, and Non-goals; English mirrors the structure. Design authority links exact `plans/fullstack-design` sections. Verification names commands, data, and expected output.

## Closed sets

- Issue status: `backlog` / `ready` / `in-progress` / `done`
- Milestone status: `planned` / `active` / `done`
- Priority: `P0` / `P1` / `P2` (P0 highest)

## IDs, dependencies, and progression

- A draft with null `github.number` stays in backlog until sync backfills it.
- At most one `bootstrap: true` issue exists, in the first milestone; remove it after backfill.
- Equal priorities serialize across milestones; within-milestone demotion follows the existing rule.
- Active work requires completed dependencies; dependency cycles are red.

## Gates

| Check | Purpose |
|---|---|
| `pnpm verify:flow` | Offline rules, stable IDs, dependencies, sections, state machine |
| `verify-flow --diff <base>` | `(#N)` titles, issue eligibility, diff scope coverage |
| `pnpm verify:flow-online` | GitHub milestone/issue/PR consistency |
| `pnpm test:gates` | Flow parsing, dependencies, bodies, GitHub rendering, retirement, routing |

## GitHub synchronization

`pnpm flow:sync` is the sole GitHub writer. It creates and updates issue bodies from the detailed Chinese files, maps status, and only with explicit `-- --retire-missing` closes open remote issues/milestones absent locally. **Remote objects are closed, never deleted.** gh authentication is required; `FLOW_TOKEN` enables strong Projects v2 checks.

## Tooling

`pnpm flow:new-issue -- --milestone <id> --id <milestone-NN> --priority <P0> --slug <kebab> --title <Chinese title> --title-en <English title> --scope <glob,glob> --depends <id,id>` scaffolds three files; complete the body contract before readiness.
