# M24 Single-ref clones and iterative pushes for evolution run workspaces

English | [中文](m24-milestone.md)

```yaml flow
kind: milestone
id: m24
title: M24 自进化 Run 单 ref 克隆与推送
status: done
github:
  number: 30
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/30
```

## Goal

Fetch only the target ref (branch, tag, or full commit) for an evolution run workspace instead of running a full `--mirror` of the target repository: a cold clone drops to the 10MB class and finishes within the 60-second bound. A single-ref clone must still create the run branch, write patches, commit, pass ancestry validation, and push. Run events and structured logs must answer whether each ls-remote / clone / fetch / push used the proxy, the proxy state, and any fallback reason.

## Scope

The run-workspace cache and clone in `apps/api/app/third_party_api/git/`, proxy observability, wiring in `apps/api/app/main.py`, the `HE_GIT_PUSH_URL` setting, the run-event payload, focused unit tests, deployment and workspace documentation, the Agent Note, and the flow files.

## Acceptance

- A cold run-workspace clone no longer runs `--mirror`; tags, branches, and full commits fetch only the target ref.
- The cache hits and refreshes per target + ref; a changed ref triggers an explicit fetch; transient failures keep complete objects, and partial directories are cleaned up for retry.
- A single-ref clone can create the run branch, write a patch, commit, pass ancestry validation, and push; the push target and credentials policy is explicit, and third-party targets without write access do not get branches pushed by default.
- Run events record the ref, cache hit, duration, and proxy state (disabled / closed / open), plus a bounded per-operation `gitOperations` list; structured logs can be filtered by runId.
- Existing API, contract, frontend, and evaluation contracts stay unchanged.

## Non-goals

No changes to the egress proxy (m18) or target-content reads (m19); no changes to patch generation, evaluation, UI, or the `preview/*` contract; no change to proxy selection or circuit-breaking beyond observability.
