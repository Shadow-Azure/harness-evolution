# M22 Single-ref clone and push for evolution runs

English | [中文](m22-milestone.md)

```yaml flow
kind: milestone
id: m22
title: M22 自进化 Run 单 ref 克隆与推送
status: planned
github:
  number: 30
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/30
```

## Goals

Make an evolution run workspace fetch only the target ref (branch / tag / full commit) instead of every ref: a cold clone drops from the 290MB class to the 10MB class and fits the 60-second budget. Branch creation, patch, commit, ancestry checks, and push continue to work from that ref, and run events expose the ref, cache state, and proxy state.

## Scope

The workspace cache and clone in `apps/api/app/third_party_api/git/`, wiring in `apps/api/app/main.py`, run events, related unit tests, the Agent Note, and flow files; documentation and minimum validation for the push target / `HE_GIT_PUSH`.

## Acceptance

- A run workspace cold clone no longer runs `--mirror`; tags, branches, and full commits fetch only the target ref. Measured v6.4.1: single-branch full history about 7.1MB / 2.5s; depth 1 about 3.3MB / 2.3s.
- The cache keys on target + ref, with an explicit fetch when the ref changes; transient failures keep complete objects, and partial caches have a clear cleanup and retry policy.
- A single-ref clone supports creating the run branch, writing a patch, committing, passing ancestry checks, and pushing; the push target and credential policy are explicit, and the default does not push a branch to a third-party repository without write access.
- Run events record the ref, cache hit, duration, and proxy state (disabled / closed / open), so proxy usage is answerable without SSH.
- Existing API, contracts, frontend, and evaluation contracts are unchanged.

## Non-goals

No proxy (m18) or target-content (m19) changes; no patch generation, evaluation, UI, or `preview/*` sync-contract changes.
