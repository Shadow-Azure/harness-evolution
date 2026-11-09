# Agent Note: V2 workspace context and object-level attribution

Status: proposed

English | [中文](2026-11-09-v2-workspace-attribution.md)

## Problem

The existing authentication, Session browser, error details, and evolution pages are reusable, but all business data currently occupies one global scope. A single attribution view also cannot express one bad case's relationship to multiple target versions. Adding independent workspace filters to each page or overwriting one attribution per target would mix caches, authorization decisions, and historical conclusions across boundaries.

## Decision

- V2 introduces current-workspace context between global identity and business pages. Production routes carry a `workspaceId` prefix, and frontend query keys, API queries, and run snapshots include the same context. Legacy routes redirect only when ownership is unambiguous.
- Retain login, refresh Cookie, Bearer access token, Session overview, execution flow, problem description, and target/version/window selection. Workspace management moves to a separate settings area without burdening core navigation.
- Workspace roles are admin, member, and viewer. The single global admin creates workspaces; workspace admins have every operation only inside their workspace. Public registration remains disabled.
- Attribution becomes an evolution-run artifact keyed by bad case, target identity and version, policy version, and model version. A non-target conclusion is object-scoped and does not change the shared bad case facts.
- Launch preview first associates Sessions where the target appears, then selects potential bad cases using the default or a versioned custom policy. Cache reuse returns only the latest successful attribution for the same complete key.

## Alternatives considered

- Independent workspace filters per page: locally simple, but page changes and deep links can lose context; rejected.
- Copying a bad case per target: simplifies lists but destroys fact identity and multiplies statistics and permission synchronization; rejected.
- Keeping attribution before launch: preserves the read model but cannot express target association, potential policies, or cache hits; rejected.
- Building V2 as a separate dark-themed application: discards validated visuals, authentication, and error details; rejected.

## Consequences

- Existing data needs an explicit default workspace, and every cross-domain read needs workspace constraints and server-side membership checks.
- Error details need paginated attribution summaries and individual detail queries, while problem descriptions and execution-flow components remain reusable.
- Evolution runs must persist candidate sets, trigger evidence, policy versions, and cache versions so history remains explainable and replayable.
- This decision currently applies only to `plans/v2-ui-prototype/`; production contracts, schema migrations, and authorization require follow-up issues.
