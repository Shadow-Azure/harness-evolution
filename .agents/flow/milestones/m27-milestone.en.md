# M27 Project introduction and README showcase

English | [中文](m27-milestone.md)

```yaml flow
kind: milestone
id: m27
title: M27 项目介绍与 README 展示
status: done
github:
  number: 37
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/37
```

## Goals

Turn the root README from the stale "M1 engineering foundation in progress" status page into an introduction for new readers: a one-sentence positioning, core capabilities, one key product screenshot, quick start and documentation entry points. The Chinese and English sides stay paired, and the screenshot uses only local synthetic fixtures.

## Scope

`README.md`, `README.en.md`, `README.i18n.yaml`, `docs/assets/readme/**`, `scripts/doc-budgets.manifest.json`, and matching updates under `.agents/notes/**` and `.agents/flow/**`.

## Acceptance

- The README presents current V2 capabilities instead of centering on M1 status and production deployment steps.
- Exactly one product screenshot, captured from local fixture demo data; it contains no production session content, credentials or real user data.
- Both languages mirror each other, pairing is re-recorded, and document and flow gates pass; the PR explains the budget adjustment.

## Non-goals

Do not change the application UI or features; do not remove deployment, architecture or development docs from `docs/`; do not add more screenshots or video; do not commit production screenshots.
