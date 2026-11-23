# Annotate the production .env.example with required/optional and keep one template

English | [中文](bugfix-env-example-required-first.md)

```yaml flow
kind: issue
id: bugfix-28
milestone: bugfix
depends: []
priority: P2
status: in-progress
scope:
  - .env.example
  - .gitignore
  - docs/deployment.md
  - docs/deployment.en.md
  - docs/deployment.i18n.yaml
  - deploy/**
  - plans/deploy-aliyun-playbook.md
  - plans/2026-11-23-pr530-review.md
  - .agents/**
adr:
  - ../../notes/implemented/process/2026-11-23-env-example-single-template.md
github:
  number: 529
  url: https://github.com/Shadow-Azure/harness-evolution/issues/529
```

## Background

Production `.env` is read by systemd through `EnvironmentFile=`. A missing required value either makes the service fail to start or leaves a first deployment without a login-capable administrator. The existing `deploy/env.production.example` groups variables by network, data, Git, and other domains, mixing required and optional entries; an operator must cross-check `apps/api/app/config.py` to know which values cannot be empty. The user asked for a `.env.example` that puts required fields first and explains every field. systemd does not support trailing comments on assignment lines, so explanations must be standalone lines; otherwise the comment becomes part of the value.

## Goals

- Add a root `.env.example` as the single production `.env` template, with required fields first and optional fields after them.
- Put a `# 必填｜...` or `# 选填｜...` line after every variable explaining the value, its purpose, default, and constraints.
- Remove `deploy/env.production.example` and point the deployment docs, bootstrap, and playbook at the new template.
- Let `.gitignore` track the root `.env.example` while continuing to ignore a real `.env`.

## Design authority

- `apps/api/app/config.py`: `Settings` fields, defaults, production-mode validation, and startup validation.
- [deploy/harness-api.service](../../../deploy/harness-api.service): the production process reads configuration through `EnvironmentFile=/opt/harness/shared/.env`.
- [docs/deployment.en.md](../../../docs/deployment.en.md): current production layout, config injection, and release flow.
- [plans/fullstack-design/01-architecture.md](../../../plans/fullstack-design/01-architecture.md): the single-instance production architecture.

## Implementation

- `.env.example`: the required block contains `HE_PRODUCTION`, `HE_HOST`, `HE_DATA_DIR`, `HE_JWT_SECRET`, `HE_DB_URL`, `HE_ADMIN_USERNAME`, and `HE_ADMIN_PASSWORD`; optional blocks then cover authentication, database tuning, upstream services, Git, the AI Agent, and evaluation. Each assignment is followed by a required/optional explanation line.
- Remove `deploy/env.production.example` and update the template path in `docs/deployment.md` / `.en.md`, `deploy/bootstrap-server.sh`, and `plans/deploy-aliyun-playbook.md`.
- Add a `!.env.example` exception to `.gitignore`.
- Add an Agent Note recording the single-template and standalone-comment decisions.

## Implementation steps

1. Migrate the fields from `deploy/env.production.example`, reorder them as required then optional, and complete the per-field explanations.
2. Delete the old template and update the docs, bootstrap, and playbook paths.
3. Allow the root `.env.example` in `.gitignore`.
4. Add the Agent Note and re-record the bilingual documentation pair.
5. Run the documentation, flow, and gate-self-test checks.

## Dependencies and boundary

- Dependencies: none.
- Boundary: only the template, docs, and process record change. Do not change `Settings` fields, defaults, or deployment injection logic; do not write real secrets; do not add environment variables.

## Verification

```sh
pnpm lint:docs
pnpm verify:docs
pnpm verify:flow
pnpm test:gates
awk '/^[A-Z][A-Z0-9_]*=/{key=$0; getline; if ($0 !~ /^# (必填|选填)｜/) { print "missing annotation: " key; bad=1 }} END { exit bad }' .env.example
```

- All four gates are green.
- `awk` prints nothing, proving every assignment is followed by a required/optional explanation.
- The required block precedes the optional blocks in `.env.example`, and no line uses the `KEY=value # comment` form.

## Acceptance

- A root `.env.example` exists and every required field appears before the optional fields.
- Every variable has a `必填` or `选填` line explaining what to enter and why; a missing required value fails startup or leaves the first deployment without an administrator.
- `deploy/env.production.example` is gone, and the template links in `docs/deployment.md` / `.en.md`, bootstrap, and the playbook resolve.
- A real `.env` stays ignored by git while `.env.example` is tracked.
- CI is green.

## Gates and CI

- `pnpm lint:docs`, `pnpm verify:docs`, `pnpm verify:flow`, `pnpm test:gates`.
- Commit and PR titles carry `(#N)`.

## Non-goals

- Do not change `Settings` fields, defaults, startup validation, or deployment injection logic.
- Do not provide a local-development SQLite template or write real credentials.
- Do not rewrite historical `plans/` review records to the old path.
- Do not add environment variables or change the deployment pipeline.
