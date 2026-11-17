# Agent Note: GitHub state JSON boundary in flow:sync

Status: implemented

English | [中文](2026-11-17-flow-sync-gh-state-json.md)

## Problem

The `flow:sync` core orchestration accepts parsed states, but its production CLI adapter returned JSON strings from `gh` and read `.state` directly, turning every state read into `undefined`. Synchronization then sent no-op PATCH requests to historical objects whose states already matched, preventing an account that can maintain issues but cannot edit milestones from completing issue-body synchronization.

## Decision

GitHub CLI JSON decoding belongs at the adapter boundary. A strict pure function parses the string and verifies that `state` is a non-empty string; both milestone and issue read adapters parse before returning state. `runSync` continues to consume state strings, preserving its injected test surface and business state machine. A genuine state mismatch still sends PATCH and propagates permission failures.

## Alternatives considered

- Catch milestone PATCH 404 and continue: this would silently suppress genuine permission or remote-object errors, so it was rejected.
- Require every developer to receive milestone write permission: broader permissions would not correct the invalid state read, so it was rejected.
- Accept strings and objects inside `runSync`: this would leak CLI transport representation into pure orchestration, so it was rejected.

## Consequences

Remote objects whose state already matches no longer receive PATCH requests, allowing lower-privilege accounts to complete the issue synchronization they are authorized to perform. Malformed JSON or missing state now fails clearly at the adapter. A real state change still requires the corresponding GitHub permission and has no bypass.
