# 在 .gitignore 中新增全部图片类型的过滤规则

[English](bugfix-ignore-image-files.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-44
milestone: bugfix
depends: []
priority: P2
status: done
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

## 背景

日常工作和 Agent 执行会在工作区留下截图、下载图片、粘贴附件等图片文件。仓库根 `.gitignore` 此前没有覆盖任何图片扩展名，这些文件会持续出现在 `git status` 中，既干扰检视，也增加误提交的可能。仓库同时跟踪 380 张文档、检视与报告配图（约 38 MB）；这些图片已被索引，忽略规则不会影响它们。用户要求在 `.gitignore` 中新增全部图片类型的过滤规则。

## 目标

- 仓库根 `.gitignore` 覆盖常见位图与矢量图扩展名，规则在任意目录生效。
- 已跟踪图片继续跟踪、可正常修改，不执行 `git rm --cached`。
- 用 Agent Note 记录决策、被否方案与未来需要新图时的处理方式。

## 设计依据

- 仓库根 [.gitignore](../../../.gitignore)：忽略规则的唯一来源。
- [docs/AGENTS.md](../../../docs/AGENTS.md)：说明 `plans/` 的定位；其中的历史截图属于已跟踪内容，不受忽略规则影响。
- [Agent Note](../../notes/implemented/process/2026-11-23-ignore-image-files.md)：记录扩展名清单、目录例外的取舍与后果。

## 实现内容

- `.gitignore` 新增 `png`、`jpg`、`jpeg`、`jpe`、`jfif`、`gif`、`webp`、`avif`、`bmp`、`tif`、`tiff`、`ico`、`svg`、`heic`、`heif`、`apng` 规则。
- 新增双语 Agent Note，说明为什么不做目录例外、为什么不动历史图片。
- 不改动任何已跟踪文件，不引入 LFS 或图床依赖。

## 实施步骤

1. 在 `.gitignore` 末尾加入图片扩展名规则。
2. 新增 Agent Note 中英三件套并重录配对记录。
3. 用临时文件验证新规则命中，并确认已跟踪配图仍在索引。
4. 跑文档、流程与门禁自测试。

## 依赖与交付边界

- 依赖：无。
- 交付边界：只改 `.gitignore`、流程记录与 Agent Note；不清除历史图片、不迁移图床、不启用 LFS、不逐个目录设例外。

## 独立验证

```sh
touch demo.png demo.JPG demo.svg
git check-ignore -v demo.png demo.svg
git ls-files docs/assets/readme/session-overview.png
pnpm lint:docs
pnpm verify:docs
pnpm verify:flow
pnpm test:gates
```

- `git check-ignore` 命中 `.gitignore` 中的新规则。
- `git ls-files` 仍输出既有配图，说明没有被移出索引。
- 四个文档与流程门禁通过。

## 验收标准

- 根 `.gitignore` 包含上述图片扩展名规则，任意目录新建图片文件默认不被跟踪。
- 已跟踪图片的数量与索引不变，文档配图链接可达。
- Agent Note 记录决策、被否方案，以及需要新图时用 `git add -f` 或调整规则的出口。
- 文档与流程门禁通过。

## 门禁与 CI

- `pnpm lint:docs`、`pnpm verify:docs`、`pnpm verify:flow`、`pnpm test:gates`。
- 提交与 PR 标题带 `(#N)`；CI 全绿。

## 非目标

- 不清理历史图片、不改写历史。
- 不迁移图床、不启用 Git LFS。
- 不为 `docs/`、`plans/`、`reports/` 增加目录例外。
- 不改动任何已跟踪文件的内容。
