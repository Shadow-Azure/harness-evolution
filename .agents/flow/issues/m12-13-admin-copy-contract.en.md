# Align workspace-admin permission and auth-contract copy

English | [中文](m12-13-admin-copy-contract.md)

```yaml flow
kind: issue
id: m12-13
milestone: m12
depends:
  - m7-03
  - m7-09
  - m12-02
priority: P2
status: in-progress
scope:
  - apps/web/src/pages/workspaces/**
  - tests/e2e/m7-09-workspace-admin.test.mjs
  - tests/e2e/m12-13-admin-copy-contract.test.mjs
  - plans/**
  - docs/**
  - reports/**
  - .agents/flow/**
  - .agents/notes/**
adr: []
github:
  number: 340
  url: https://github.com/Shadow-Azure/harness-evolution/issues/340
```

## Background

The information architecture of workspace admin is largely aligned, but several directly correctable copy and contract-example mismatches remain:

- The prototype says an administrator may add any user, "including themselves," as a workspace administrator. Production says only "any user," understating the global administrator's ability to grant themselves a workspace-admin role.
- The prototype auth page still uses `email` and demo-account replacement language. Production authenticates with `username` and returns `accessToken`, `expiresIn`, and a user object, while the page also documents the current Cookie session.
- The prototype ingest page still shows the old snake_case `bad_cases` payload. The production contract uses `badCaseId`, `sessionId`, `badCaseType`, and other camelCase fields and explicitly rejects a body `workspace` field.

These differences require copy and fixture alignment, not auth, workspace, or ingest behavior changes.

## Goals

- Align production and prototype on the "including yourself" workspace-admin permission.
- Make the auth example match username/Cookie login and avoid implying that production supports demo-account selection.
- Make ingest examples match the current camelCase bad-case contract and retain the 422 statement for `workspace`.
- Add copy snapshots/component assertions to prevent design, page, and OpenAPI drift.
- Do not change request logic, permission decisions, or credential generation.

## Evidence screenshots

**Workspace and quota**

| Production | V2 prototype |
| --- | --- |
| [![Production workspace admin](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/prod-06-admin-spaces.jpeg)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/prod-06-admin-spaces.jpeg) | [![V2 prototype workspace admin](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/proto-06-admin-spaces.jpeg)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/proto-06-admin-spaces.jpeg) |

**Authentication**

| Production | V2 prototype |
| --- | --- |
| [![Production auth contract](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/prod-06d-admin-auth.jpeg)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/prod-06d-admin-auth.jpeg) | [![V2 prototype auth contract](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/proto-06d-admin-auth.jpeg)](https://github.com/Shadow-Azure/harness-evolution/releases/download/m12-08-evidence-d18c8d5/proto-06d-admin-auth.jpeg) |

All four are real browser-window captures at `2816×1576`. The workspace copy differs on "including yourself"; the auth structure is aligned while login fields and response examples still differ.

## Design authority

- [08 §4.2 Top-bar user area, workspace switcher, and admin page](../../../plans/fullstack-design/08-frontend-implementation.md#42-顶栏用户区空间切换器与空间管理页v2): admin structure and role copy.
- [05 §4.16 Workspaces, members, and credentials](../../../plans/fullstack-design/05-api-design.md#416-工作空间成员与凭据v2): membership and credential APIs.
- [05 §4.17 Workspace bad-case ingest](../../../plans/fullstack-design/05-api-design.md#417-bad-case-上报v2凭据鉴权): ingest request and authorization boundaries.
- [05 §4.1 Health and authentication](../../../plans/fullstack-design/05-api-design.md#41-基础端点健康检查与鉴权): login, refresh, and me contracts.
- [V2 design §4.3 Workspace-admin interaction](../../../plans/ui-prototype-v2/design-v2.md#43-空间管理交互): administrators can add any user, including themselves.

## Implementation

- Update production copy to "any user, including yourself" for adding users and granting workspace-admin roles.
- Update the prototype auth example to `username`, current access-token/session responses, and remove language that implies production can select demo accounts.
- Align prototype and production bad-case examples on the camelCase payload and the rule that workspace identity comes from URL/credential while an extra `workspace` field returns 422.
- Update stale examples in `plans/ui-prototype-v2/design-v2.md`; if production copy is already correct, add tests that lock it.
- Add string/DOM assertions for "including yourself," username, response fields, and the 422 rule.

## Implementation steps

1. Inventory permission, auth, and ingest copy across production, prototype HTML, and `design-v2.md`.
2. Add failing copy assertions for the current API fields and permission semantics.
3. Update admin and prototype copy without changing request constructors.
4. Update design examples and run `pnpm record:i18n` for affected persistent bilingual documents.
5. Run web, E2E, contract, documentation, and flow gates and verify displayed examples match sent payloads.

## Dependencies and boundary

- Dependencies: m7-03 supplies authentication, m7-09 supplies workspace admin, and m12-02 supplies live external-contract verification; all are done.
- Boundary: update copy, examples, and tests only. Do not change APIs, Cookies, RBAC, or credential lifecycle.
- Prototype demo accounts may be removed or marked as legacy artifacts, never presented as a production account-enumeration feature.
- If implementation and contract already diverge, stop copy changes and report the drift instead of hiding it.

## Verification

```sh
pnpm test:web -- apps/web/src/pages/workspaces
pnpm test:e2e -- --pattern m12-13
pnpm contract:check
pnpm lint:docs
pnpm verify:flow
```

- Production and prototype both state that administrators may add users including themselves.
- The auth example uses `username` and shows the current access-token/session contract.
- Ingest examples use camelCase and state that body `workspace` returns 422.
- Displayed copy matches OpenAPI/generated types with no contract drift.

## Acceptance

- Workspace administration, ingest, and auth copy match current behavior.
- The prototype no longer implies email/snake_case fields that implementation does not use.
- Copy tests lock permission wording, login fields, response fields, and the 422 boundary.
- No request payload, Cookie, or workspace permission behavior changes.
- Contract, web, E2E, documentation, and flow gates pass.

## Gates and CI

- `pnpm test:web`, `pnpm test:e2e`, `pnpm contract:check`, `pnpm typecheck`, `pnpm lint:docs`, `pnpm verify:docs`, and `pnpm verify:flow`.
- Run `pnpm record:i18n -- <pair>` and commit pairing metadata for any persistent bilingual document.

## Non-goals

- Do not add account selectors, enumeration, or demo login to production.
- Do not change login, refresh, logout, Cookie, or SSO behavior.
- Do not change ingest auth, credential rotation, quota, or RBAC behavior.
- Do not redesign the workspace-admin layout.
