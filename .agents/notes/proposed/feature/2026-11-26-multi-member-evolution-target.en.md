# Agent Note: Multi-member evolution target in one repository

Status: proposed

English | [中文](2026-11-26-multi-member-evolution-target.md)

## Problem

An evolution target is one configuration for one object today: the unique constraint is `(workspace_id, object_type, object_name)`, and the scope `sub_dir`, the validation/test project IDs, and the binding attribution all hang off the same row. One repository often holds several skills and agents (for example `skills/deep-research` and `skills/code-review`) that share the repository, baseline, and evaluation projects, and whose bad cases often come from the same sessions. Splitting them into one configuration per object duplicates the repository, test projects, and attribution Skill, scatters bad-case ownership across several configurations, and lets one run evolve only one object; the patch may change only one directory and the evaluation submits only one asset.

## Decision

One `evolution_targets` row remains one evolution target, but object identity moves down to a new `evolution_target_members`: the configuration row keeps only shared fields (repository, baseline, validation/test project IDs, primary metric, attribution Skill, enabled), while member rows carry `object_type / object_name / sub_dir` and each member's definition snapshot. The launch wizard, run snapshot, patch scope, evaluation assets, and the seven steps all work per configuration: runs gain `evolution_run_targets` for the member snapshot, `MatchCondition` takes a member list, `allowed_paths` returns the union of member directories, and one evaluation submits all member assets.

Members must share the repository (one run has one `base_commit`), and a member belongs to exactly one configuration (otherwise bad cases and attribution reports become ambiguous). During the compatibility window the legacy `evolution_targets` columns are kept for one release and written with the first member, historical runs without member rows read the legacy columns, and a single-member configuration keeps a byte-identical attribution cache key. The evaluation platform's `asset_paths` is a multi-valued list and one launch accepts one template, so the test projects and primary metric must be shared, which matches this decision.

## Alternatives considered

One configuration per member with a multi-select wizard over objects in the same repository: duplicated configuration, scattered bad-case ownership, and an artificial "primary object"; the user rejected that interaction. Batch form filling only with one object per run: does not evolve the group. A JSON column for members on the configuration: no unique constraint or per-member join, so binding and overview would have to unpack JSON. Letting one member belong to several configurations: bad cases and attribution reports become ambiguous, and launching from a bad case cannot pick a configuration. Pushing the test projects down to members: one launch accepts one template, so several members cannot be evaluated in one evaluation.

## Consequences

Configuration, binding, launch, patch, evaluation, and presentation move from single-object to the two levels "configuration plus member", concentrated in the configuration service, binding worker, potential matching, launch and prepare, patch scope, evaluation request, and run projection; the migration backfills the member table and the run-member table. V1 read endpoints and historical runs rely on the legacy columns for one release, and the next release may tighten them. A member cannot be used by two configurations; the constraint is validated globally on save. Cross-repository members are out of scope.
