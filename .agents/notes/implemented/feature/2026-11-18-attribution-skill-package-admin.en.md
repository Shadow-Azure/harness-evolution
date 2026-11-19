# Agent Note: Separate workspace attribution Skill packages from executable revisions

Status: implemented

English | [中文](2026-11-18-attribution-skill-package-admin.md)

## Problem

Intranet attribution capabilities are delivered as directories containing `SKILL.md` and supporting files, while the existing attribution Skill registry is designed for executable revisions, Golden evaluation, and target bindings. It cannot retain a complete directory or let workspace administrators inspect and retire uploaded assets. Registering every uploaded package as an executable revision would turn asset administration into a production release path that bypasses quality gates; storing files only on disk would omit workspace ownership, uploader, and current selection state.

## Decision

- Add a separate workspace Skill package asset layer: the database stores package name, uploader, file count, ZIP size, hash, relative path, `SKILL.md`, and one effective binding; files are isolated under `attribute/{workspace_id}/{package_id}`.
- `attribute-badcases/SKILL.md` is the undeletable default prompt source. The API projects it as a virtual `attribute-badcases` package and generates its ZIP on demand; a workspace falls back to it when no custom binding exists or the active package is deleted.
- An upload must remain below compressed/expanded size and file-count limits and contain exactly one UTF-8 `SKILL.md`; its frontmatter `name` is the workspace-unique identity. Absolute paths, `..`, drive prefixes, symlinks, and encrypted members are rejected.
- Viewers may inspect prompts and download packages; only space admins or the global admin may upload, activate, and delete. Uploads remain inactive until an administrator explicitly switches.
- Package effectiveness belongs only to workspace asset configuration and does not automatically create or bind an existing executable revision. Production Runs continue to use the registry's Golden promotion and frozen-revision rules.

## Alternatives considered

- **Write ZIP content directly into `attribution_skill_revisions.content` and auto-bind it**: rejected. A complete directory does not fit the JSON revision model, and auto-binding bypasses Golden evaluation.
- **Store only a ZIP BLOB**: rejected. Large binaries enlarge transactions and backups, while download and prompt reads would repeatedly decompress; the database retains queryable metadata and a prompt snapshot only.
- **Activate immediately after upload**: rejected. A workspace administrator should inspect the package name, file statistics, and prompt before changing configuration, and an accidental upload must not change the current selection.
- **Allow overwrite by name**: rejected. Implicit replacement would change current selection and download content without a revision; the current flow requires deletion before re-upload.

## Consequences

- Workspace administration gains an “Attribution Skill” tab and Bearer/RBAC APIs, while the default package guarantees every workspace can display an effective prompt.
- The filesystem is the source of truth for package content, and the database is the source of truth for metadata and selection. A failed database write removes the extracted directory; deletion removes the record and binding before best-effort directory cleanup.
- Production execution and asset configuration remain two explicit paths. A future intranet adapter must add a controlled publication step between an evaluated package and an immutable revision instead of reusing the current activation action.
- ZIP downloads are regenerated from validated directories and never expose server paths; the default package follows the same download shape.

The built-in package includes SKILL.md and the canonical writer from the same source used for execution. New uploads live under the workspace’s `attribute_skill/uploads`. Historical records continue to resolve their stored relative paths.
