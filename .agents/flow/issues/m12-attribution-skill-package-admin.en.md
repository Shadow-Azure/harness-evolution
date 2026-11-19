# Workspace attribution Skill package management

English | [中文](m12-attribution-skill-package-admin.md)

```yaml flow
kind: issue
id: m12-23
milestone: m12
depends:
  - m12-17
  - m12-21
priority: P2
status: in-progress
scope:
  - .gitignore
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - docs/**
  - attribute/**
  - attribute-badcases.md
  - .agents/flow/**
  - .agents/notes/**
  - plans/**
adr: []
github:
  number: 374
  url: https://github.com/Shadow-Azure/harness-evolution/issues/374
```

## Background

The attribution Skill backend already supports revisions and bindings, but workspace administrators can only select existing revisions from the evolution-target page; they cannot upload, inspect, download, or delete a complete Skill folder. Intranet attribution Skills are delivered as directories containing `SKILL.md` and supporting files, so the product needs a workspace-isolated, auditable, ZIP-safe asset entry point that also makes the currently effective prompt visible to administrators.

## Goals

- Add an attribution Skill tab to workspace administration with ZIP upload, listing, download, deletion, and explicit activation.
- Persist package metadata, workspace ownership, uploader, and active state while storing files under workspace-isolated directories below the repository `attribute/` root.
- Ship a built-in `attribute-badcases` default package and fall back to it when no custom package is active or the active package is deleted.
- Validate ZIP paths, file counts, expanded size, and the single `SKILL.md` requirement to prevent traversal, archive bombs, and incomplete packages.

## Design authority

- [05 API design](../../../plans/fullstack-design/05-api-design.md): workspace scope, bearer/RBAC, stable errors, and upload/download boundaries.
- [08 frontend implementation](../../../plans/fullstack-design/08-frontend-implementation.md): workspace administration IA, query caching, and mutation feedback.

## Implementation

- Add a package table, migration, repository, file-storage service, and workspace-scoped APIs.
- Parse the frontmatter name and `SKILL.md` after upload, recording uploader, file count, ZIP size, content hash, and relative storage path.
- Enforce one active custom package per workspace; the default package is a virtual read-only asset and cannot be deleted.
- Add frontend APIs, a composable, and a workspace administration tab showing the upload entry, package inventory, and effective prompt.

## Implementation steps

1. Add migration, model, storage validation, and default-asset fallback.
2. Implement and contract-test list/upload/download/activate/delete APIs.
3. Regenerate OpenAPI contracts and implement the workspace administration flow.
4. Add backend/frontend tests, architecture documentation, and an Agent Note.

## Dependencies and boundary

- Dependencies: m12-17 and m12-21.
- Boundary: do not integrate an intranet LLM/Agent, edit archive files online, or bypass the Golden promotion gate to change existing Run executor selection.

## Verification

```sh
pnpm test:api -- tests/attribution_skill_packages
pnpm --filter @harness/web exec vitest run src/pages/workspaces/Admin.test.ts
pnpm contract:check
pnpm lint:docs
```

- API tests cover the default package, upload validation, workspace isolation, download, activation, and deletion; frontend tests cover reader and administrator flows; contract and documentation gates pass.

## Acceptance

- Every workspace always resolves one effective package and its `SKILL.md`.
- A valid ZIP has matching list statistics and download bytes; traversal, oversized archives, and missing or duplicate `SKILL.md` return stable errors without leaving partial files.
- Only workspace administrators can upload, activate, and delete; viewers can read the list and effective prompt.
- Deleting the active custom package falls back to `attribute-badcases`, and the default package cannot be deleted.

## Gates and CI

- `test:api`, Web Vitest, `contract:check`, `typecheck:web`, `lint:api`, `lint:web`, `lint:docs`, and `verify:flow`.

## Non-goals

- No browser-based Skill editor, execution of uploaded code, logging of raw package contents, or automatic production binding of an unevaluated package.
