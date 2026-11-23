# Agent Note: Ignore all image file types by default

Status: implemented

English | [中文](2026-11-23-ignore-image-files.md)

## Problem

Daily work and agent runs leave screenshots, downloaded images, and pasted attachments in the working tree. The repository root `.gitignore` previously covered no image extension, so those files kept showing up in `git status`, creating noise and a risk of accidental commits. The repository also tracks 380 documentation, review, and report images (about 38 MB); those historical evidence files must stay readable and editable. Ignore rules only affect untracked files, and `git rm --cached` must not be used to drop them from the index.

## Decision

Add a group of common image extensions to the repository root `.gitignore`: `png`, `jpg`, `jpeg`, `jpe`, `jfif`, `gif`, `webp`, `avif`, `bmp`, `tif`, `tiff`, `ico`, `svg`, `heic`, `heif`, and `apng`. The rules apply at any depth, carry no directory exceptions, and remove no tracked file.

## Alternatives considered

Ignoring only fixed directories (for example `reports/`) does not satisfy "all image file types" and leaves noise elsewhere. Adding negative exceptions for `docs/`, `plans/`, and `reports/` would keep future screenshots trackable, but those are exactly the directories where images appear most, so the requirement would be hollow; existing tracked images are unaffected by ignore rules anyway, so exceptions protect nothing. Moving images to Git LFS addresses large-file storage, not untracked-file filtering, and adds an external remote dependency. Using `git rm --cached` to clean historical images would delete images referenced by documentation and review records and break readability, so it is explicitly rejected.

## Consequences

New image files are ignored by default. When a documentation or review change really must commit a new image, it needs an explicit `git add -f`, or this note and the ignore rules should be revisited first. The 380 tracked images remain unaffected and can still be modified and committed. Rules are enumerated by extension, so a new image format needs one more line; platforms with case-sensitive paths (such as Linux) do not automatically match uppercase extensions, while this macOS checkout's case-insensitive index does. The repository history is unchanged, and no LFS or image-hosting dependency is introduced.
