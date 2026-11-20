# Bugfix problem fixes

English | [中文](bugfix-milestone.md)

```yaml flow
kind: milestone
id: bugfix
title: Bugfix 问题修复
status: active
standing: true
github:
  number: 34
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/34
```

## Goals

Own every subsequent bugfix issue under one milestone instead of opening a new milestone per problem; each issue describes one independently acceptable problem, and its fix surface is bounded by that issue's scope.

This milestone is a standing bucket: it stays active/open after all of its issues are done and does not close when one bugfix completes; only a roadmap decision to retire it sets its status to done.

## Scope

Subsequent bugfix issues and their changes under `apps/web/**`, `apps/api/**`, `tests/**`, `scripts/**`, `plans/**`, `.agents/**`, and similar areas; each issue's allowed modification surface is still bounded by its own `scope`.

## Acceptance

Each bugfix issue delivers its implementation, verification, and screenshot evidence against its own acceptance criteria; final acceptance is the requester's confirmation that the whole flow currently has no problems, and the issue stays open until that confirmation.

## Non-goals

No new milestone per single problem; no closing this milestone because one bugfix completed; no unrelated refactors, redesigns, or cross-module re-layouts inside a bugfix issue; no production Session content, screenshots, or credentials in the repository.
