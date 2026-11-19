# 空间归因 Skill 包管理

[English](m12-attribution-skill-package-admin.en.md) | 中文

```yaml flow
kind: issue
id: m12-23
milestone: m12
depends:
  - m12-17
  - m12-21
priority: P2
status: in-progress
scope:
  - .gitignore
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - docs/**
  - attribute/**
  - attribute-badcases.md
  - .agents/flow/**
  - .agents/notes/**
  - plans/**
adr: []
github:
  number: 374
  url: https://github.com/Shadow-Azure/harness-evolution/issues/374
```

## 背景

现有归因 Skill 后端支持版本和绑定，但空间管理员只能在进化对象页选择已有 revision，不能上传、检查、下载或删除完整 Skill 文件夹。内网归因 Skill 以包含 `SKILL.md` 及辅助文件的目录交付，需要一个空间隔离、可审计且能安全处理 ZIP 的资产入口，并让当前生效提示词对管理员可见。

## 目标

- 在空间管理中提供归因 Skill Tab，支持 ZIP 上传、列表、下载、删除和显式切换生效项。
- 将 Skill 包元数据、空间关系、上传者和当前生效状态持久化，文件落在仓库 `attribute/` 根目录下的空间隔离目录。
- 内置 `attribute-badcases` 默认包；没有自定义生效项或删除当前项时自动回退默认包。
- 校验 ZIP 路径、文件数量、总大小和唯一 `SKILL.md`，避免路径穿越、压缩炸弹与不完整包。

## 设计依据

- [05 API 设计](../../../plans/fullstack-design/05-api-design.md)：空间作用域、Bearer/RBAC、稳定错误响应和上传/下载接口边界。
- [08 前端实现](../../../plans/fullstack-design/08-frontend-implementation.md)：空间管理信息架构、Query 缓存和写操作反馈。

## 实现内容

- 新增 Skill 包表、迁移、repository、文件存储 service 与空间级 API。
- 上传后解析 frontmatter 名称和 `SKILL.md`，记录 uploader、文件数、ZIP 大小、内容 hash 与相对存储路径。
- 生效切换采用单空间单 active 约束；默认包为虚拟只读资产，不允许删除。
- 新增前端 API、composable 和空间管理 Tab，展示上传按钮、资产列表及当前生效提示词。

## 实施步骤

1. 建立迁移、模型、存储校验和默认资产回退。
2. 实现 list/upload/download/activate/delete API 与契约测试。
3. 生成 OpenAPI 契约并实现空间管理交互。
4. 补齐前后端测试、架构文档和 Agent Note。

## 依赖与交付边界

- 依赖：m12-17、m12-21
- 非目标：不接入内网 LLM/Agent，不在线编辑 ZIP 内文件，不绕过 Golden 发布门禁改变现有 Run 的执行器选择。

## 独立验证

```sh
pnpm test:api -- tests/attribution_skill_packages
pnpm --filter @harness/web exec vitest run src/pages/workspaces/Admin.test.ts
pnpm contract:check
pnpm lint:docs
```

- API 用例覆盖默认包、上传校验、空间隔离、下载、切换和删除；前端用例覆盖只读与管理员交互；契约和文档门禁全绿。

## 验收标准

- 每个空间始终能解析一个当前生效包及其 `SKILL.md`。
- 合法 ZIP 的列表统计与下载内容一致，恶意路径、超限包、缺失或重复 `SKILL.md` 返回稳定错误码且不留残缺文件。
- 只有空间管理员能上传、切换和删除；viewer 可读取列表和当前提示词。
- 删除当前自定义包后回退 `attribute-badcases`，默认包不可删除。

## 门禁与 CI

- `test:api`、Web Vitest、`contract:check`、`typecheck:web`、`lint:api`、`lint:web`、`lint:docs`、`verify:flow`。

## 非目标

- 不提供浏览器内 Skill 编辑器，不执行上传代码，不把原始包内容写入日志，不自动把未评测包绑定到生产 Run。
