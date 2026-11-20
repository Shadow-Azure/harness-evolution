# Agent Note: Launch wizard version becomes an input-first combobox

Status: implemented

English | [中文](2026-11-19-launch-wizard-ref-input.md)

## Problem

Step 1 of "start self-evolution" only allowed a version to be picked from a tag dropdown. A person could not validate evolution on a working branch or an untagged commit without creating a tag first. The target configuration `defaultRef` explicitly accepts a branch or tag, but that value was not guaranteed to appear in the launch wizard: when the repository already had tags, a branch baseline was hidden by the tag list. The V2 prototype and `08 §9.2` also described the version as a tag list at the time, so the gap existed in the prototype, the design documents, and production.

## Decision

- The V2 prototype launch wizard now uses an input-first editable combobox. The input itself is the submitted `targetVersion`; the dropdown only offers the current target's tags and `defaultRef` as suggestions, and picking one is optional.
- The default is `defaultRef`, falling back to the first tag. When `defaultRef` is a branch and is not in the tag list, it still appears as a "baseline" suggestion instead of being silently replaced by a tag.
- Git ref format is validated on "next: associate sessions" and again on the final "start self-evolution": non-empty, at most 96 characters, no whitespace/`..`/`@{`/`~^:?*[` or other illegal characters, and no trailing `-`, `/`, `.` or `.lock`; a failure stays on step 1 with a field error. After the format passes, the server uses git to decide whether the ref exists in the repository: run `git rev-parse --verify <ref>^{commit}` on the cached mirror, refreshing the mirror once when the remote ref is missing; tags, branches, and commits must all resolve to a commit. A missing ref returns `TARGET_CONTENT_UNRESOLVED` (reason `ref_not_found`); an unreachable or timed-out repository uses the same error (reason `repo_unreachable` / `content_timeout`). Both return to step 1. Only then does the server resolve `SKILL.md` / `AGENT.md` at that ref and compute the body hash; it never falls back to a guessed tag.
- Version identity remains the body hash; tags are suggestions and display values only, not a change to matching or cache semantics. Production `LaunchWizard.vue` now follows the same pattern: an input with a tag suggestion menu, whose value is submitted directly as `targetVersion`; the prototype's demo ref check remains illustrative, while production checks the real repository with git.
- `plans/fullstack-design/08 §9.2`, `05 §4.11`, `15`, and `design-v2` now state that the `versions` endpoint returns tags only as suggestions and that `targetVersion` accepts tags, branch names, and commit SHAs.

## Alternatives considered

- **Keep tag-only and require a tag to be created first**: rejected. It pushes version-management cost onto the person and does not explain why target configuration accepts a branch or tag; it is worse for unpublished commits.
- **Keep the select and add a separate "custom" input**: rejected. Two controls for one value create two paths, and defaulting and error ownership become harder to explain; an input-first combobox is more direct.
- **Validate on every keystroke and report errors per character**: rejected. Intermediate states of a branch name are necessarily invalid; character-level errors create noise. Validating at the two real submission points, next and final start, is sufficient.
- **Simulate server-side ref existence in the prototype**: rejected. The prototype has no repository data; fabricated rejections would hide the real server resolution semantics. The prototype demonstrates format validation and interaction only; existence belongs to the server.

## Consequences

- The prototype accepts `main`, `feature/foo`, and `a3f9c21`, while tags remain selectable from the dropdown; a malformed ref, or one absent from the demo repository data, shows an inline error and does not advance to step 2. Production uses an input with a suggestion menu and keeps the typed value on blur/submit; server `TARGET_CONTENT_UNRESOLVED` (`ref_not_found` / `repo_unreachable`) returns to step 1.
- The design documents no longer promise "version = tag list"; a later production implementation can reuse the input-first combobox pattern already used by target configuration.
- Production `LaunchWizard.vue` now follows this decision; prototype and production share the same suggestion source (`defaultRef` + tags), but production existence checks come from the real repository rather than demo refs.
- The boundary between the client format check and the server `TARGET_CONTENT_UNRESOLVED` / `REPO_INVALID` responses still needs production tests: the client rejects malformed refs, while a missing ref or unreadable content is returned by the server and returns the flow to step 1.
