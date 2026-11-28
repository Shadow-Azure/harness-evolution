# Session overview mislabels flow and context as errors and attribution labels differ across four views

English | [中文](bugfix-attribution-category-display.md)

```yaml flow
kind: issue
id: bugfix-77
milestone: bugfix
depends: []
priority: P2
status: in-progress
scope:
  - attribute-badcases/SKILL.md
  - attribute-badcases/make_probe_report.py
  - attribute/README*
  - apps/api/app/api/problems.py
  - apps/api/app/service/bad_cases/**
  - apps/api/app/service/problems/schemas.py
  - apps/api/tests/**
  - apps/web/src/components/bad-cases/**
  - apps/web/src/pages/errors/**
  - apps/web/src/pages/evolution/**
  - apps/web/src/pages/overview/components/PotentialCaseTable*
  - apps/web/src/router/deepLink*
  - apps/web/src/utils/**
  - packages/contracts/**
  - tests/e2e/**
  - .github/workflows/ci.yml
  - .agents/flow/issues/bugfix-attribution-category-display*
  - .agents/notes/implemented/**
adr: []
github:
  number: 631
  url: https://github.com/Shadow-Azure/harness-evolution/issues/631
```

## Background

A report classified as `flow` shows 是问题-错误 in the Session overview and 流程 in its detail view. The same mismatch affects `context`. The matrix shows actual Chinese UI text at `main@cc5b7726`. Five synthetic attributed reports were stored in local SQLite and the Vue views were rendered with the read data.

| `attribute_type` | Attribution detail | Evolution attribution step | Session overview list | Workspace potential case category |
| --- | --- | --- | --- | --- |
| `model` | 模型问题 | 模型 | 是问题-模型问题 | `model` |
| `prompt` | prompt缺失某些提示词 | prompt | 是问题-prompt缺失某些提示词 | `prompt` |
| `error` | 错误 | 错误 | 是问题-错误 | `error` |
| `flow` | 流程 | 流程 | **是问题-错误** | `flow` |
| `context` | 上下文 | 上下文 | **是问题-错误** | `context` |

The Skill uses `prompt` for missing, incorrect, redundant and ambiguous instructions. The detail and list labels imply missing instructions only. The workspace overview prints the raw API value. [Skill taxonomy](https://github.com/Shadow-Azure/harness-evolution/blob/cc5b7726f30f15fe75ba4f89552a2454f48c8c7b/attribute-badcases/SKILL.md#L274-L288) · [Workspace category cell](https://github.com/Shadow-Azure/harness-evolution/blob/cc5b7726f30f15fe75ba4f89552a2454f48c8c7b/apps/web/src/pages/overview/components/PotentialCaseTable.vue#L373-L382)

## Goals

Use the same category names in all four views: 模型问题, 提示词问题, 错误, 流程 and 上下文. The Session list can keep its 是问题- prefix.

The attribution Skill must produce reproducible report IDs that fit the 64-character storage contract. Previously stored long IDs must open from the list and from direct links using their original values.

## Design authority

[Frontend design §5 Session browser, §7.3 attribution tab and §10 run detail](../../../plans/fullstack-design/08-frontend-implementation.md). The conclusion describes responsibility for the selected target. The category describes the kind of attributed problem.

## Implementation

Storage, the detail API and the Session list’s `analysis.attributeType` preserve all five categories. The list projection handles model and prompt explicitly and returns `analyzed_issue_error` for both flow and context. The UI badge consumes that display state. [Backend projection](https://github.com/Shadow-Azure/harness-evolution/blob/cc5b7726f30f15fe75ba4f89552a2454f48c8c7b/apps/api/app/service/bad_cases/service.py#L110-L116) · [List badge](https://github.com/Shadow-Azure/harness-evolution/blob/cc5b7726f30f15fe75ba4f89552a2454f48c8c7b/apps/web/src/components/bad-cases/badCaseDisplay.ts#L23-L34) · [Detail labels](https://github.com/Shadow-Azure/harness-evolution/blob/cc5b7726f30f15fe75ba4f89552a2454f48c8c7b/apps/web/src/pages/errors/components/attributionDisplay.ts#L30-L39)

## Implementation steps

1. Extend `DisplayState` with `analyzed_issue_flow` and `analyzed_issue_context`. Map all five categories explicitly and preserve existing state values. Run `pnpm contract:generate` to update OpenAPI and generated types.
2. Use an exhaustive frontend label map keyed by the API category type. Share it across detail, evolution and potential case views. Have the Session list compose its existing prefix with the same category names and add badges for the two new states.
3. Parameterize SQLite, API and component checks for all five categories across the four views. Cover null categories for `non_target` and `inconclusive` as well.

## Dependencies and boundary

Use the existing report script and `probe_reports.attribute_type`. The script accepts `unknown` when a category is undetermined. An attributed report requires one of the five categories. The business column is null for non-target and inconclusive reports. Existing five-category reports benefit from the read-side fix.

## Verification

Create one attributed report per category. Compare detail `category`, Session list `analysis.attributeType` and `analysis.displayState`, then inspect all four views. For a flow report the current tuple is `flow / flow / analyzed_issue_error`. Expect `analyzed_issue_flow` in the third position and 是问题-流程 in the Session list.

## Acceptance

- All five labels match the expected values in all four views. Flow and context produce distinct Session list badges.
- Each prompt label reads 提示词问题 and covers missing, incorrect, redundant and ambiguous instructions. The workspace overview displays Chinese for all five categories.
- Null categories display no problem-category badge. Detail preserves the distinct non-target and inconclusive verdicts. CI runs the parameterized backend and frontend regression cases.

- Generate and verify a report with a long target name and a 64-character bad case ID. Exercise pagination, workspace detail, legacy reads and browser links with historical composite IDs.

## Gates and CI

`pnpm test:api`, `pnpm test:web`, `pnpm typecheck:web` and `pnpm contract:check`. The cross-stack browser test ingests bad cases before binding the attribution Skill, then verifies that the resulting report is readable. Shared CI allows 20 minutes per complete serial browser run.

## Non-goals

Database migrations, production backfills, historical reruns and changes to model attribution decisions are outside this issue.
