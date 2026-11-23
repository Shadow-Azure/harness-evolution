# Ignore all image file types in .gitignore

English | [中文](bugfix-ignore-image-files.md)

```yaml flow
kind: issue
id: bugfix-44
milestone: bugfix
depends: []
priority: P2
status: in-progress
scope:
  - .gitignore
  - .agents/flow/issues/bugfix-ignore-image-files*
  - .agents/notes/implemented/process/2026-11-23-ignore-image-files*
adr:
  - ../../notes/implemented/process/2026-11-23-ignore-image-files.md
github:
  number: 549
  url: https://github.com/Shadow-Azure/harness-evolution/issues/549
```

## Background

Daily work and agent runs leave screenshots, downloaded images, and pasted attachments in the working tree. The repository root `.gitignore` previously covered no image extension, so those files kept showing up in `git status`, disturbing review and increasing the chance of accidental commits. The repository also tracks 380 documentation, review, and report images (about 38 MB); those files are already indexed, and ignore rules do not affect them. The user asked for ignore rules covering all image file types in `.gitignore`.

## Goals

- Cover common raster and vector image extensions in the repository root `.gitignore`, effective at any depth.
- Keep already-tracked images tracked and editable; do not run `git rm --cached`.
- Record the decision, rejected alternatives, and the path for committing a new image in an Agent Note.

## Design authority

- Repository root [.gitignore](../../../.gitignore): the single source of ignore rules.
- [docs/AGENTS.md](../../../docs/AGENTS.md): defines the role of `plans/`; historical screenshots there are tracked content and are not affected by ignore rules.
- [Agent Note](../../notes/implemented/process/2026-11-23-ignore-image-files.en.md): records the extension list, the directory-exception trade-off, and consequences.

## Implementation

- Add rules for `png`, `jpg`, `jpeg`, `jpe`, `jfif`, `gif`, `webp`, `avif`, `bmp`, `tif`, `tiff`, `ico`, `svg`, `heic`, `heif`, and `apng` to `.gitignore`.
- Add a bilingual Agent Note explaining why there are no directory exceptions and why historical images are untouched.
- Do not modify any tracked file, and do not add an LFS or image-hosting dependency.

## Implementation steps

1. Append the image extension rules to `.gitignore`.
2. Add the Chinese/English Agent Note trio and re-record its pairing record.
3. Verify the new rules with temporary files and confirm tracked images remain in the index.
4. Run the documentation, flow, and gate self-tests.

## Dependencies and boundary

- Dependencies: none.
- Boundary: change only `.gitignore`, the flow record, and the Agent Note; do not clean historical images, migrate to image hosting, enable LFS, or add per-directory exceptions.

## Verification

```sh
touch demo.png demo.JPG demo.svg
git check-ignore -v demo.png demo.svg
git ls-files docs/assets/readme/session-overview.png
pnpm lint:docs
pnpm verify:docs
pnpm verify:flow
pnpm test:gates
```

- `git check-ignore` matches the new rules in `.gitignore`.
- `git ls-files` still prints the existing image, so it was not removed from the index.
- All four documentation and flow gates pass.

## Acceptance

- The root `.gitignore` contains the image extension rules, and new image files at any depth are untracked by default.
- The tracked image count and index are unchanged, and documentation image links stay reachable.
- The Agent Note records the decision, rejected alternatives, and the exit path for committing a new image (`git add -f` or adjusting the rules).
- Documentation and flow gates pass.

## Gates and CI

- `pnpm lint:docs`, `pnpm verify:docs`, `pnpm verify:flow`, `pnpm test:gates`.
- Commit and PR titles carry `(#N)`; CI is green.

## Non-goals

- Do not clean historical images or rewrite history.
- Do not migrate to image hosting or enable Git LFS.
- Do not add directory exceptions for `docs/`, `plans/`, or `reports/`.
- Do not change the content of any tracked file.
