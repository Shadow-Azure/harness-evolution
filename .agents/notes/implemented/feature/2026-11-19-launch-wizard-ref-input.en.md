# Agent Note: Launch wizard version becomes an input-first combobox

Status: implemented

English | [中文](2026-11-19-launch-wizard-ref-input.md)

## Problem

Step 1 of "start self-evolution" only allowed a version to be picked from a tag dropdown. A person could not validate evolution on a working branch or an untagged commit without creating a tag first. The target configuration `defaultRef` explicitly accepts a branch or tag, but that value was not guaranteed to appear in the launch wizard: when the repository already had tags, a branch baseline was hidden by the tag list. The V2 prototype and `08 §9.2` also described the version as a tag list at the time, so the gap existed in the prototype, the design documents, and production.

## Decision

- The V2 prototype launch wizard now uses an input-first editable combobox. The input itself is the submitted `targetVersion`; the dropdown only offers the current target's tags and `defaultRef` as suggestions, and picking one is optional.
- The default is `defaultRef`, falling back to the first tag. When `defaultRef` is a branch and is not in the tag list, it still appears as a "baseline" suggestion instead of being silently replaced by a tag.
- Git ref format is validated on "next: associate sessions" and again on the final "start self-evolution": non-empty, at most 96 characters, no whitespace/`..`/`@{`/`~^:?*[` or other illegal characters, and no trailing `-`, `/`, `.` or `.lock`; a failure stays on step 1 with a field error. The server resolves `SKILL.md` / `AGENT.md` at that ref and computes the body hash; resolution failure returns to step 1 and never falls back to a guessed tag.
- Version identity remains the body hash; tags are suggestions and display values only, not a change to matching or cache semantics. Production `LaunchWizard.vue` has not followed yet: this Note records the prototype and design decision, and the production implementation needs its own flow issue / PR.
- `plans/fullstack-design/08 §9.2`, `05 §4.11`, `15`, and `design-v2` now state that the `versions` endpoint returns tags only as suggestions and that `targetVersion` accepts tags, branch names, and commit SHAs.

## Alternatives considered

- **Keep tag-only and require a tag to be created first**: rejected. It pushes version-management cost onto the person and does not explain why target configuration accepts a branch or tag; it is worse for unpublished commits.
- **Keep the select and add a separate "custom" input**: rejected. Two controls for one value create two paths, and defaulting and error ownership become harder to explain; an input-first combobox is more direct.
- **Validate on every keystroke and report errors per character**: rejected. Intermediate states of a branch name are necessarily invalid; character-level errors create noise. Validating at the two real submission points, next and final start, is sufficient.
- **Simulate server-side ref existence in the prototype**: rejected. The prototype has no repository data; fabricated rejections would hide the real server resolution semantics. The prototype demonstrates format validation and interaction only; existence belongs to the server.

## Consequences

- The prototype accepts `main`, `feature/foo`, and `a3f9c21`, while tags remain selectable from the dropdown; an illegal ref shows an inline error and does not advance to step 2.
- The design documents no longer promise "version = tag list"; a later production implementation can reuse the input-first combobox pattern already used by target configuration.
- Production `LaunchWizard.vue` is still tag-only. This PR only changes the prototype and design documents and must not be treated as a production fix; #382 continues to track implementation.
- The boundary between the client format check and the server `TARGET_CONTENT_UNRESOLVED` / `REPO_INVALID` responses still needs production tests: the client rejects malformed refs, while a missing ref or unreadable content is returned by the server and returns the flow to step 1.
