# m3-01 Session Browser

English | [中文](m3-01-session-browser.md)

```yaml flow
kind: issue
id: m3-01
milestone: m3
depends:
  - m2-06
  - m2-07
priority: P0
status: done
scope:
  - AGENTS.md
  - apps/web/**
  - packages/contracts/**
  - fixtures/**
  - scripts/**
  - tests/**
  - .github/workflows/ci.yml
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
  - plans/**
  - reports/**
adr: []
github:
  number: 41
  url: https://github.com/Shadow-Azure/harness-evolution/issues/41
```

## Background





m3-01 connects real canonical sessions to the prototype's two-column browser so operators can triage, search, filter, and inspect an overview in one screen.

## Goals





- Deliver the 360px session sidebar, real white cards, dual density bars, and the right-hand session overview.
- Persist search, status, sort, and selected session in the URL with refresh and history restoration.
- Provide independent loading, empty, and retryable error states without requesting the future Agent tree.
- Display the real `stats.badCases` value without fabricated counts or frontend data.

## Design authority





- [03 §5 Session browser](../../../plans/fullstack-design/03-frontend-architecture.md)
- [08 §5 component tree](../../../plans/fullstack-design/08-frontend-implementation.md)
- [02 §2.1 F3/F4](../../../plans/fullstack-design/02-features.md)
- [Prototype acceptance baseline](../../../plans/14-15-ui-prototype/harness-evolution.html)

## Implementation





- Prototype session cards with status, title, time, repo, duration, tool/agent counts, five statistics, and two density bars.
- Overview title/meta/status, nine statistics, readable token counts, and an explicit future Agent-tree placeholder.
- Debounced search, status chips, sorting, automatic first selection, and `/sessions/:sid` deep links.
- Prototype light tokens, two columns at 1408px, and a single-column mobile layout at 390px.

## Implementation steps





1. Add failing MSW and real seeded E2E tests first.
2. Implement the sessions API/query layer, cards, overview, and URL state.
3. Verify computed styles, URL restoration, and responsive behavior with four canonical sessions.

## Dependencies and boundary





- Depends on m2-06 and m2-07.
- The Agent execution graph and error-detail page remain owned by later issues.

## Verification





```sh
pnpm test:api -- tests/m3-01-session-browser
pnpm test:db
pnpm test:web
pnpm test:e2e -- m3-session-browser
```

- Seeded CI E2E passes.
- Local list and overview statistics match the API.

## Acceptance





- Search, sorting, and selection survive refresh.
- List and overview expose retryable states.

## Gates and CI





- Component tests, query gates, and real-browser computed-style regression.

## Non-goals

- Do not render the Agent execution graph or implement the error-detail page.
