# Agent Note: GitHub state JSON boundary in flow:sync

Status: implemented

English | [中文](2026-11-17-flow-sync-gh-state-json.md)

## Problem

The `flow:sync` core orchestration accepts parsed states, but its production CLI adapter returned JSON strings from `gh` and read `.state` directly, turning every state read into `undefined`. Synchronization then sent no-op PATCH requests to historical objects whose states already matched, preventing an account that can maintain issues but cannot edit milestones from completing issue-body synchronization.

## Decision

The CLI adapter decodes GitHub JSON. It reads state for milestones and both state and nullable milestone number for issues. When either issue field differs, `runSync` updates both in one PATCH. It reconciles the body separately. Scoped sync validates the selected issue and milestone numbers before writing. An issue-only selection updates those issues. A milestone can be selected on its own. Metadata-only synchronization preserves the original GitHub acceptance notes when closing historical issues.

## Alternatives considered

- Catch milestone PATCH 404 and continue: this would silently suppress genuine permission or remote-object errors, so it was rejected.
- Require every developer to receive milestone write permission: broader permissions would not correct the invalid state read, so it was rejected.
- Accept strings and objects inside `runSync`: this would leak CLI transport representation into pure orchestration, so it was rejected.

## Consequences

Records with matching metadata skip the metadata write. The adapter rejects malformed responses and missing fields. GitHub still enforces permission checks on writes.
