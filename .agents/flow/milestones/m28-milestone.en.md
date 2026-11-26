# M28 Multi-member evolution target in one repository

English | [中文](m28-milestone.md)

```yaml flow
kind: milestone
id: m28
title: M28 同仓多成员进化对象
status: planned
github:
  number: 38
  url: https://github.com/Shadow-Azure/harness-evolution/milestone/38
```

## Goals

- Upgrade the evolution target from a single object to "one configuration plus several members in one repository": repository, baseline, test projects, primary metric, and attribution Skill are shared, while each member freezes its definition and associates its own bad cases.
- One run evolves the whole group per configuration: member snapshot, patch scope as the union of member directories, and one evaluation submitting all member assets.
- Legacy columns keep the first member for one release, historical configurations are backfilled as single-member, and V1 read endpoints plus historical runs stay unchanged.

## Scope

Models, migrations, repositories, configuration, binding, launch, matching, patch, evaluation, and projection in `apps/api`; `packages/contracts`; configuration, wizard, run detail, and overview in `apps/web`; `tests/e2e`; `plans/fullstack-design/18-multi-member-evolution-target.md`; prototype and flow files.

## Acceptance

- One configuration saves two members from the same repository; duplicate members, members owned by another configuration, and missing test projects are rejected.
- The wizard selects one configuration; run detail shows members, shared test projects, and the change scope; steps 2 and 3 show the hit member.
- Binding attribution runs once per configuration over the member union; a single-member cache key stays byte-identical.
- One evaluation submits all member assets; a missing member directory fails prepare.
- Historical configurations and runs stay compatible; gates and PR screenshots are complete.

## Non-goals

Do not change the evaluation platform asset contract; do not support cross-repository members; do not let one member belong to several configurations; do not change the attribution Skill protocol, the V1 six-step mapping, or "one evaluation per member".
