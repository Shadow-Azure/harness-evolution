# M7 身份与空间边界

English | [中文](m7-milestone.md)

```yaml flow
kind: milestone
id: m7
title: M7 身份与空间边界
status: active
github:
  number: 17
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/17
```

## Goals

Establish one global admin, workspace roles, the auth-provider seam, and end-to-end workspace isolation.

## Scope

Identity, workspaces, membership, routing, administration, and ingest credentials.

## Acceptance

The permission matrix and invisible workspace behavior are automated; clients recover identity and spaces only from auth/session.

## Non-goals

No knowledge object or workspace partition of raw traces.
