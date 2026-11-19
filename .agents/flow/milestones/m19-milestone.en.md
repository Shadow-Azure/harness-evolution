# M19 Production single-ref target-content reads

English | [中文](m19-milestone.md)

```yaml flow
kind: milestone
id: m19
title: M19 生产目标内容单 ref 读取
status: planned
github:
  number: 26
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/26
```

## Goals

Stop mirroring a target repository in full when production reads a single ref: cache a shallow repository per (repository, ref), fetch only the target ref, and lazily fetch only one blob when reading the file. Egress proxying is a later independent task and is not part of this phase.

## Scope

Read-only target-content reads under `apps/api/app/third_party_api/git/`, their unit tests, the Agent Note, and the flow files.

## Acceptance

- A cold read of one tag, branch, or full commit fetches only that ref (`--depth 1 --single-branch --filter=blob:none`) instead of `--mirror`; `git show` lazily fetches only the target blob.
- Tags and branches stay current, full SHAs reuse the cache, and missing refs/files plus network failures keep the existing stable classifications.
- Old mirror cache directories are unaffected and need no data migration; the `read_file` interface and the 20-second bound stay unchanged.

## Non-goals

No egress proxy, Secret, or Xray deployment (design in #394); no change to the synchronous `preview/*` contract or asynchrony, no frontend change, and no change to the run-workspace mirror and push model.
