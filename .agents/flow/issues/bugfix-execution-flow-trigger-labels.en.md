# Execution-flow subagent trigger labels show task descriptions instead of skill/subagent names

English | [中文](bugfix-execution-flow-trigger-labels.md)

```yaml flow
kind: issue
id: bugfix-03
milestone: bugfix
depends: []
priority: P2
status: ready
scope:
  - apps/web/**
  - plans/ui-prototype-v2/**
  - tests/e2e/**
  - plans/**
  - .agents/**
adr: []
github:
  number: 439
  url: https://github.com/Shadow-Azure/harness-evolution/issues/439
```

## Background

On 2026-11-20 the user reviewed the trigger labels on the execution-flow main chain in the production "Session errors" page and asked whether this position shows the skill name or the subagent name. The screenshot corresponds to production Session `90e6c9f9-6f2e-4f7b-b313-a616993975e5` (workspace `OpenSpec-cn_SWE-bench`, bad case `[SWE-bench] astropy__astropy-13579 · not_scored`); the red boxes mark six purple diamond nodes on the structure-tree main chain, reading "Implement sliced WCS …", "Spec compliance revie…", "Add towncrier changel…", "Code quality review o…", "Verify fix and check …", and "Final rev…".

Production full-page screenshot (the red boxes are the user's annotation of the checked position):

![Production "Session errors" execution-flow main chain](https://github.com/Shadow-Azure/harness-evolution/releases/download/execution-flow-label-evidence-20261120/shot.jpg)

Zoomed labels:

![Production execution-flow main chain: six subagent trigger nodes show task descriptions](https://github.com/Shadow-Azure/harness-evolution/releases/download/execution-flow-label-evidence-20261120/prod-labels.jpg)

The raw production data (`GET /api/workspaces/{wid}/sessions/{sid}/tree`) shows all six events have `kind: "agent"`, with `name` and `desc` stored separately:

| Line | `event.name` (subagent name) | `event.desc` (task description) | Shown on the chain |
|---:|---|---|---|
| 369 | `code-generator` | Implement sliced WCS world_to_pixel fix | Implement sliced WCS … |
| 386 | `spec-reviewer` | Spec compliance review of task 1 | Spec compliance revie… |
| 387 | `code-generator` | Add towncrier changelog fragment | Add towncrier changel… |
| 398 | `code-quality-reviewer` | Code quality review of the fix | Code quality review o… |
| 492 | `code-generator` | Verify fix and check regressions | Verify fix and check … |
| 510 | `code-quality-reviewer` | Final review of overall implementation | Final rev… |

## Finding: what the V2 prototype shows here

The V2 prototype `plans/ui-prototype-v2/harness-evolution.html` uses the same branch in its structure-tree main chain (`chainOf`):

```js
const text = e.kind === "skill"
  ? (e.name || "skill")
  : clipName(e.desc || e.name || e.kind);
```

- **Skill trigger**: a green diamond node shows `event.name`, the skill name (the prototype samples are `deep-research` and `superpowers:dispatching-parallel-agents`).
- **Subagent trigger**: a purple diamond node shows `event.desc || event.name`, the task description (the prototype samples are `检索模型层三方法`, `检索EverMind与Hermes`, etc.); the subagent type/name appears on the child agent card below, such as `general-purpose · 检索模型层三方法 · L33`.

V2 prototype structure tree (same `chainOf`; green is a skill name, purple is a subagent description):

![V2 prototype structure-tree main chain](https://github.com/Shadow-Azure/harness-evolution/releases/download/execution-flow-label-evidence-20261120/proto-tree-2x.png)

Zoomed at the same position:

![V2 prototype structure-tree main chain: skills show names, subagents show descriptions](https://github.com/Shadow-Azure/harness-evolution/releases/download/execution-flow-label-evidence-20261120/proto-labels-2x.png)

The direct answer to the user's question is therefore:

1. The position marked in the screenshot shows **subagent task descriptions**, not skill names and not subagent names. This Session has no skill trigger events, so no skill name appears on the main chain.
2. The V2 prototype also shows task descriptions for subagent triggers; only skill triggers show the skill name. Production and the V2 prototype choose the same field, so this is **not a production regression**.
3. The label rule is still inconsistent: skill nodes use a stable name, while subagent nodes use free-form descriptions. Descriptions are clipped at 22 characters (`clipName`), so the main chain cannot reliably identify which subagent fired; the name is only available on the child agent card below.

This is the implementation rule for this issue: a trigger node exists to identify *which object* fired, so it uses the name consistently, with the description as supporting information. If the requester explicitly chooses to keep "description first", record that on this issue and close it without implementing the change.

## Goals

- Skill trigger nodes on the structure-tree main chain show the skill name; subagent/workflow trigger nodes show the subagent name (`event.name`, falling back to `agentType`/`kind`), with the task description in the hover title, or render a compact `name · desc`.
- The V2 prototype and production share one rule; the prototype sample data gains a subagent `name` instead of using `desc` as the node label.
- Do not change event parsing, trigger coordinates, ordering, the `×N` gap rule, the lane DAG, or the child agent card layout.

## Design authority

- [03 §8.3 Agent execution-flow graph: lane DAG + structure tree](../../../plans/fullstack-design/03-frontend-architecture.md): the structure tree keeps using `chainOf` in `tree/layout.ts`; the V2 prototype is the visual baseline.
- V2 prototype `plans/ui-prototype-v2/harness-evolution.html`: the node-chain comment ("skill / subagent triggers are each one node") and the `chainOf` branch ("skill → name / others → desc"); in the prototype `TREE` sample, subagent events only have `desc`, and the child agent card shows `type · desc · L`.
- Production implementation `apps/web/src/components/agent-tree/tree/layout.ts` `chainOf`: `event.kind === "skill" ? event.name : event.desc || event.name`.
- Server label rule `_label` in `apps/api/app/service/sessions/service.py`: the stable subagent label is `agent.name`, while `desc` is the task description; the tree API returns both.
- Prior art [#276](https://github.com/Shadow-Azure/harness-evolution/issues/276): execution-flow lane DAG and structure-tree switching.

## Implementation

Implement the rule "skill name + subagent name; description in the tooltip". If the requester explicitly chooses to keep the status quo, close this issue without implementing the change.

- `apps/web/src/components/agent-tree/tree/layout.ts` `chainOf`:
  - skill: keep `event.name || "skill"`.
  - agent/workflow: use `event.name || event.agentType || event.desc || event.kind`; `clipName` still truncates only the final text.
  - Include both name and desc in the node `title`, together with `L{line}`, so the description remains readable on hover.
- `apps/web/src/components/agent-tree/tree/nodes/AgentNode.vue`: consume only the chain item's `name`/`title`; no layout change. Confirm the pill width still adapts through `measure` when names get longer.
- V2 prototype `plans/ui-prototype-v2/harness-evolution.html`:
  - Add `name` to the `TREE` agent events (using the sample subagent type/name, such as `general-purpose`/`Explore`) and make `chainOf` follow the same rule as production.
  - Keep the child agent card's `type · desc · L` information; do not drop the description.
- Tests:
  - Add a case to `apps/web/src/components/agent-tree/tree/layout.test.ts`: an agent event with `name: "code-generator"` and `desc: "Implement sliced WCS world_to_pixel fix"`; assert the chain item text is `code-generator` and the `title` contains the desc; keep a skill-event case asserting the skill name.
  - Assert in `apps/web/src/components/agent-tree/tree/AgentTree.test.ts` or an e2e test that the rendered `.rf-cnode` text is not the long description.
  - Update prototype snapshots or visual assertions if any exist.
- Docs: if the rule needs to be long-lived, add one line to `plans/fullstack-design/03-frontend-architecture.md` §8.3: "trigger nodes show the name; desc is hover-only supporting text".

## Implementation steps

1. Confirm the shared rule: skill name + subagent name; description as a tooltip.
2. Change `chainOf` and the `title`, and add unit tests.
3. Update the V2 prototype `TREE` data and `chainOf`, then capture the same Session shape (with both skill and subagent triggers) for comparison.
4. Run the focused unit test, typecheck, lint, focused e2e, and `pnpm verify:flow`.
5. Attach Before/After evidence to the PR: the structure-tree main chain for Session `90e6c9f9-…` (Before: clipped task descriptions; After: `code-generator`/`spec-reviewer` names), plus the same position in the V2 prototype.

## Dependencies and boundary

- Dependencies: none; unrelated to the lane DAG.
- Boundary: only the structure-tree main-chain trigger labels, the V2 prototype sample, and the corresponding tests; no API/tree-contract change, event parsing change, `×N` rule change, lane DAG change, or child agent card hierarchy change.
- Do not commit production Session content or screenshots to the repository; keep Before/After images in PR/Release evidence.
- If the requester decides to keep "description first", close this issue recording that rule and do not implement the change.

## Verification

```sh
pnpm --filter @harness/web exec vitest run src/components/agent-tree/tree/layout.test.ts
pnpm typecheck:web
pnpm lint:web
pnpm test:e2e -- "execution-flow-trigger-names"
pnpm verify:flow
```

- Open the structure tree for `90e6c9f9-6f2e-4f7b-b313-a616993975e5` with production-shaped data: the six subagent nodes on the main chain show `code-generator`, `spec-reviewer`, and `code-quality-reviewer` instead of descriptions such as `Implement sliced WCS …`; the hover `title` still contains the original description.
- A Session with skills (V2 prototype sample `050b81ba-…`) still shows `deep-research`, `superpowers:dispatching-parallel-agents`, and other skill names on the main chain.
- The V2 prototype at the same position shows the same name rule; the child agent card still shows `type · desc · L`.
- The unit tests, typecheck, lint, focused e2e, and `pnpm verify:flow` are all green.

## Acceptance

- Skill trigger nodes on the structure-tree main chain show the skill name; subagent/workflow trigger nodes show the subagent name; the description no longer occupies the main-chain label but is readable in the `title`.
- Production and the V2 prototype follow the same rule, verifiable from screenshots; no new clipping or pill overlap.
- A regression test covers the case where name and desc differ, so the desc cannot silently return to the main label.
- If the requester keeps the status quo, close this issue as "kept as-is" and preserve this finding.

## Gates and CI

- `pnpm verify:flow` (registration of this issue)
- `pnpm --filter @harness/web exec vitest run src/components/agent-tree/tree/layout.test.ts`
- `pnpm typecheck:web`, `pnpm lint:web`
- Focused `pnpm test:e2e -- "execution-flow-trigger-names"`
- The PR must include Before/After screenshots and the V2 prototype comparison (UI change)

## Non-goals

- No changes to event parsing, trigger coordinates, ordering, the `×N` rule, or the lane DAG.
- No change to the child agent card's `type · desc · L` hierarchy.
- No new icons/legend/colors and no overall execution-flow re-layout.
- No production data, screenshots, or credentials in the repository.
