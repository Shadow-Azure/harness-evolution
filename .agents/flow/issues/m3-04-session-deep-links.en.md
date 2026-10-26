# m3-04 Session Deep Links

English | [中文](m3-04-session-deep-links.md)

```yaml flow
kind: issue
id: m3-04
milestone: m3
depends:
  - m3-03
priority: P0
status: done
scope:
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - reports/**
  - docs/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 44
  url: https://github.com/Shadow-Azure/harness-evolution/issues/44
```

## Background

The Session browser and Agent flow already use real data and interactions, but the selected Agent and evidence position live only in memory. Refresh, new windows, and browser history cannot restore the same view, and there is no stable URL parsing boundary.

## Goals





- Treat `/sessions/:sid?agent=&evidence=` as the single source of state.
- Use explicit page or inline errors for invalid parameters and stale Agents without crossing Sessions.
- Provide pure parsing and ownership-resolver seams for the later `/errors?case=&tab=` route.

## Design authority





- [05 §5 深链契约](../../../plans/fullstack-design/05-api-design.md)
- [08 §6.2 深链状态](../../../plans/fullstack-design/08-frontend-implementation.md)
- [09 R6 风险](../../../plans/fullstack-design/README.md)

## Implementation





- Strictly parse, canonicalize, and validate `sessionId/agent/evidence/case/tab`.
- Restore Agent and evidence from the URL, write node selection back to the URL, and preserve the position across refresh, new windows, and back/forward.
- Clear invalid Agent state with an inline notice; keep the Agent and clear out-of-range evidence.
- Provide only a bad-case ownership resolver seam; m4-02 drives the real cross-Session 409 from API data.

## Implementation steps





1. Write failing parser, page restoration, history, and new-window tests first.
2. Implement URL-derived state, post-tree validation, and node write-back.
3. Verify refresh, new windows, and the 390px prototype shell with real four-Session data.

## Dependencies and boundary





- 依赖：m3-03
- 交付边界：只交付本 issue 的能力；未列入验收的相邻能力留给依赖或后续 issue。

## Verification





```sh
pnpm test:web -- deepLink sessions
pnpm typecheck:web
pnpm test:e2e --pattern "deep links survive"
pnpm build
pnpm verify:bundle
```

- Invalid parser input triggers neither detail nor tree requests.
- Refresh, new windows, and back/forward restore the Session, Agent, and evidence.
- A failed current-Session tree does not apply stale deep state; a successful retry restores it.

## Acceptance





- Deep links are shareable, Agent/evidence recovery is stable, and resources never leak across Sessions.

## Gates and CI





- Parser unit tests plus real-Chrome E2E and existing typecheck/build/bundle gates.

## Non-goals

- No short-link service.
- Do not register `/sessions/:sid/errors` or fabricate a bad-case ownership response in m3-04.
