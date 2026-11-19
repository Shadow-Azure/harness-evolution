# M13 Attribution identity and post-process anchors

English | [中文](m13-milestone.md)

```yaml flow
kind: milestone
id: m13
title: M13 归因身份与后处理锚点
status: done
github:
  number: 21
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/21
```

## Goals

Make skill/agent/knowledge file matching content-addressed by the normalized body hash, and give post-processed bad cases with no resolvable reported object an explicit "last" semantics instead of relying on runtime cache paths, raw content hashes, or a missing-anchor birth fallback.

## Scope

Skill/agent/knowledge file matching, tag/document-revision to body-hash resolution, session association, post-process trigger points, cache keys, contract/UI display, parser version and replay, tests and migration; design-doc review precedes implementation.

## Acceptance

Skill/agent/knowledge file matching no longer includes the runtime source path; skill/agent tags and the knowledge document revision resolve to the same body hash as the trace definitionHash/documentRevision; post-processed cases with no resolvable object use an explicit post-process trigger and participate in potential matching as "after the object"; legacy path+body revisions have a defined compatibility and replay boundary; design docs, Note, and test plan agree.

## Non-goals

No knowledge UI selector (knowledge remains API-configured/API-launched); no private-repository credentials; no rewrite of the rule-v1 attribution categories; no code before the design-doc review.
