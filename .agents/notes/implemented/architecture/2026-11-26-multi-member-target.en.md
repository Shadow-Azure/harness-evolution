# Agent Note: multiple same-repository members as one evolution target

Status: implemented

English | [中文](2026-11-26-multi-member-target.md)

## Problem

One repository often ships several skills/agents that share the repository, baseline, test projects, and attribution Skill, and whose bad cases come from the same Sessions. Before this change one `evolution_targets` row carried one object, with a unique `(workspace_id, object_type, object_name)` rule, while scope, test projects, and the binding lived on that row. Configuring a group together therefore required N configurations: shared fields were duplicated, bad-case ownership was split, one run could target only one object, and patch and evaluation covered one directory. The obvious shortcut—storing members in a JSON column—cannot enforce member uniqueness or join per member.

## Decision

- Add `evolution_target_members` (`target_id`, `seq`, object identity, `sub_dir`, frozen definition) and `evolution_run_targets` (the run's member snapshot); add `object_type/object_name/object_revision` to `evolution_run_candidates`. Shared fields stay on `evolution_targets`, and the legacy object columns keep writing the first member for one compatibility window.
- On save the service validates every member's name and subdirectory and rejects duplicates inside the configuration; a `(workspace_id, object_type, object_name)` unique index on the member table guarantees a member belongs to only one configuration, returning `409 MEMBER_ALREADY_CONFIGURED` anchored at `members[i].objectName`.
- Saving validates the repository with one `git ls-remote` and freezes each member's `{sub_dir}/SKILL.md` or `AGENT.md`. The binding snapshot stores `members[]`; the matcher condition carries `targets[]`, so any member occurrence associates a Session, each case compares against its own object's entry point, and reports are written under the case's object or owning member. A single-member configuration keeps a byte-identical cache key.
- The launch wizard selects a configuration and sends `targetId`. Creating a run writes `run_targets` in the same transaction; prepare checks every member directory with `git cat-file` and fails with `stage="subdirectory"` when one is missing; patch `allowed_paths` and evaluation `asset_paths` cover all members, and commit subjects and prompts list them.
- Projections become two-level "configuration + members": the catalog gains `targets[]`, run cards/detail gain `targets[]` and `workspace.subDirs`, steps 1/2/3 show members, the overview renders one row per configuration with merged member rows, and the case table labels the hit member with `object_name`.

## Alternatives considered

- **One configuration per member plus a multi-select wizard**: rejected by the user; it duplicates configuration, splits bad-case ownership, and forces a "primary object".
- **Batch form only, run stays single-object**: does not solve "evolve them together".
- **Members in a JSON column**: cannot enforce uniqueness or join per member, and both binding and overview would have to unpack JSON.
- **Cross-repository members**: one run has one `base_commit`; multiple repositories need a multi-repository run model outside this issue.
- **Per-member test projects or evaluations**: the evaluation platform accepts one template and one metric per launch; multiple assets are path overrides under that template.

## Consequences

- The legacy columns keep writing the first member for V1 reads and historical runs; revision 0035 backfills historical configurations as single-member configurations and historical runs into `run_targets`.
- Each member's definition is frozen independently, and changing the configuration resets the binding generation; single-member behavior and cache keys are unchanged.
- The overview deduplicates the same case/version across members and exposes members as chips and a case-table column.
- A failed background binding still records the whole batch and retries within the same generation; completed cases are not repeated.
- Tightening or dropping the legacy columns, cross-repository members, and per-member evaluation projects are left to a later version.
