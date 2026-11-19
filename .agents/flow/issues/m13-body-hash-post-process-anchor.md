# 归因身份改为归一化 body hash 与后处理锚点

[English](m13-body-hash-post-process-anchor.en.md) | 中文

```yaml flow
kind: issue
id: m13-01
milestone: m13
depends: []
priority: P2
status: in-progress
scope:
  - .agents/flow/**
  - .agents/notes/**
  - plans/fullstack-design/**
  - plans/**
  - docs/architecture.md
  - docs/architecture.en.md
  - docs/architecture.i18n.yaml
  - scripts/doc-budgets.manifest.json
  - apps/api/**
  - apps/api/alembic/**
  - apps/api/tests/**
  - apps/web/src/**
  - packages/contracts/**
  - tests/**
  - fixtures/**
adr:
  - ../../notes/implemented/architecture/2026-11-18-body-hash-attribution-post-process.md
github:
  number: 368
  url: https://github.com/Shadow-Azure/harness-evolution/issues/368
```

## 背景

2026-11-18 的生产实测中，目标 `skill / systematic-debugging` 在 `v6.4.1` 下第 2 步关联 0 个 Session：4 个已同步 Session 全部 skipped，18 个待同步。轨迹事件只有 `definitionHash=8e54…` 与 `objectRevision=digest:3643…`；后者包含运行时注入的 skill source path。该 path 是 `.../claude-plugins-official/superpowers/6.4.1/skills/systematic-debugging/SKILL.md` 一类插件 cache 路径，既不是稳定相对路径，也没有落库；target 无法从 `repoUrl/subDir/ref` 复算同一个 revision。owner 已确认 target 应使用 `superpowers` `main`。eval trace 已收到：trace 的 skill body hash 是 `8e54…`；main 的 `SKILL.md` 整文件 hash 是 `a9a7…`，去掉 YAML frontmatter 后 body hash 正好是 `8e54…`；v6.4.1 的整文件 `9080…` 是同一 body 加 frontmatter。根因是 target resolver 对整文件 hash、未剥 frontmatter；修复后 resolver 与 parser 都得到 `digest:8e54…`，source 对齐成立，M13 验收项可关闭。

同时，当前把 `eventIndex=-1` 当作“锚点缺失/异常”，并退化为上报 Agent 的出生点（主 Agent 为 Session 开始）。生产 22 条 case 都是 discovery + agent + main 上报；按现规则永远落在目标对象之前，potential=0。“后处理上报”没有独立语义，无法解释也无法按“对象之后”参与归因。

设计文档与实现目前是 path+body 身份（`docs/architecture.md:42`、`15 §9.2`、`06 §7.5`、`07 §5.12`），而 skill/agent/知识库的文件匹配都应收敛到 `sha256(normalize_definition_body(body))`：skill `SKILL.md`、agent `AGENT.md`/`agent.md`、knowledge 文档文件读。当前 target 内容解析只覆盖 skill 的 tag 文件，knowledge 的文档匹配仍走 `provider:`/original revision；issue 需要把三类对象的统一匹配键、tag/文档 revision 解析、兼容边界和迁移写进设计文档后再实现。代码现状 `parser_version` 已是 5（M9-05 知识库）；新身份需要 5→6。knowledge 裸 revision 需要 `KnowledgeContentSource`：生产未绑定文档 Provider 时只能 `digest:`/`provider:` 直接启动，裸 revision 返回 `TARGET_CONTENT_UNRESOLVED`。

## 目标

- 将 skill/agent/知识库的**文件匹配键**统一为 `sha256(normalize_definition_body(body))`：skill 取 `SKILL.md`、agent 取 `AGENT.md`/`agent.md`、knowledge 取文档文件读内容；source path 只作诊断证据，不参与 revision、缓存键或匹配。skill 的身份用该 body hash；agent 的 `object_revision` 保留类型/builtin 诊断身份但匹配用 `definition_hash`；knowledge 的 `document_revision`/`object_revision` 也用归一化 body hash。
- 将进化向导选择的 tag 解释为内容来源：skill/agent 由服务端读取该 tag 下 `SKILL.md`/`AGENT.md`，knowledge 由文档 revision/内容读取，统一归一化后计算 body hash，作为 `targetRevision`；tag/文档 revision 保留为版本/显示与代码基线。knowledge 目标仍通过 API 配置/启动，向导暂不提供 knowledge 选择器。
- 将找不到上报对象的后处理 case 改为显式后处理锚点：`eventIndex=INT_MAX`、`anchorKind=post_process`、`triggeredAt=created_at`，按“对象之后”参与潜在匹配；`-1` 只保留给上报 Agent 无法解析的 unknown。
- 明确 parser 版本、存量重放、旧 path+body revision/缓存键、契约/UI 展示和测试计划；设计文档评审通过后再写代码。

## 设计依据

- [15 §9.2 对象 revision 与模型身份](../../../plans/fullstack-design/15-v1-v2-gap-analysis.md)
- [06 §7.4 问题侧口径](../../../plans/fullstack-design/06-database-design.md)、[§7.5 V2 口径](../../../plans/fullstack-design/06-database-design.md)
- [05 §4.20 自进化预览与启动](../../../plans/fullstack-design/05-api-design.md)、[§3.4 问题与归因 DTO](../../../plans/fullstack-design/05-api-design.md)
- [07 §2.6 多 runtime parser 工厂](../../../plans/fullstack-design/07-backend-implementation.md)、[§5.12 潜在匹配](../../../plans/fullstack-design/07-backend-implementation.md)、[§5.13 归因生成与缓存](../../../plans/fullstack-design/07-backend-implementation.md)
- [08 前端实现](../../../plans/fullstack-design/08-frontend-implementation.md)
- [架构：证据与 revision](../../../docs/architecture.md)
- [Agent Note：body hash 身份与后处理锚点](../../notes/implemented/architecture/2026-11-18-body-hash-attribution-post-process.md)

## 实现内容

- 设计文档：更新上述 15/06/05/07/08 章节与 `docs/architecture.md`（含英文侧），写清 skill/agent/知识库统一的 body hash 文件匹配、tag/文档 revision 解析、后处理锚点、兼容与迁移；新增 proposed Agent Note 记录决策与被否方案。
- 后续代码（本 issue 追踪，不在设计文档 PR 内）：parser 的 skill 身份、agent `definition_hash`、knowledge 文件读 revision 统一为归一化 body hash，并递增 parser version；target 内容解析器按 tag 读取 `SKILL.md`/`AGENT.md`、按文档 revision 读取 knowledge 内容，归一化、算 hash、缓存与稳定错误；matcher 接受 body hash 与 legacy path+body（过渡）并实现 post-process 锚点；候选/归因快照记录 `anchorSource`；契约、API DTO、前端展示与测试同步。
- 迁移：存量 claude-code 会话按 parser version 重放 skill/agent/knowledge；parser_version 5→6；旧 path+body revision 保留历史，新 run 只写归一化 body hash；旧缓存键不复用；`probe_reports.object_version` 长度 96 足够。knowledge 裸 revision 需要文档 Provider；当前生产未绑定，`digest:`/`provider:` 可直接启动。

## 实施步骤

1. 建立 M13 issue 与 proposed Note；按本 issue 更新 15/06/05/07/08、`docs/architecture.md` 及英文侧、i18n 配对；提交 docs-only PR 评审。
2. 评审通过后实现 parser body-only revision、version bump 与重放；补单元/fixture 测试。
3. 实现 target 内容 resolver：skill/agent tag→`SKILL.md`/`AGENT.md`，knowledge 文档 revision→内容；统一归一化、缓存、超时、稳定错误；补 golden hash 测试，确认与已知轨迹 `definitionHash`/`documentRevision` 一致。
4. 实现 matcher 的 body hash 匹配与 post-process 锚点；更新候选/归因快照、契约与前端展示。
5. 跑迁移、重放与跨栈测试；更新文档中的状态与命令。

## 依赖与交付边界

- 依赖：M12 已完成；M13 设计评审先于代码。
- 非目标：不新增知识库 UI 选择器（knowledge 仍通过 API 配置/启动，resolver/matcher 在本切片）；不引入私有仓库凭据；不重写 rule-v1 分类；不在设计文档 PR 内改代码。

## 独立验证

```sh
pnpm verify:flow
pnpm lint:docs
pnpm verify:docs
pnpm test:gates
```

- `verify:flow` 通过，issue 三件套与 M13 milestone 一致。
- `lint:docs` / `verify:docs` 通过；`docs/architecture.md` 与英文侧、i18n 记录一致。
- 代码阶段追加：skill/agent tag 内容与 knowledge 文档内容归一化后的 sha256 等于已知轨迹 `definitionHash`/`documentRevision` 的 golden 测试；post-process case 的 `anchorKind=post_process`、`eventIndex=INT_MAX`、`triggeredAt=created_at` 与 `after_object` 的 API/集成测试。

## 验收标准

- 设计文档明确：skill/agent/知识库文件匹配都使用归一化 body hash，source path 不再参与；skill/agent tag 与 knowledge 文档 revision 是内容来源；找不到对象的后处理 case 使用显式后处理锚点并可被审计。
- 设计文档写清旧 path+body revision、parser 版本、重放、缓存键与契约/UI 的兼容边界。
- golden hash 测试证明三类 target 内容与轨迹 body 来源一致；不一致时返回稳定错误，不回退到 tag 猜测。
- 设计评审通过后再进入代码实现；本 issue 未完成前不关闭。

## 门禁与 CI

- 本 PR：`verify:flow`、`lint:docs`、`verify:docs`、`test:gates`。
- 代码阶段：`test:api`、`test:db`、`contract:check`、相关 e2e 与迁移测试；新增契约同步生成物。

## 非目标

- 不新增知识库 UI 选择器；knowledge 仍通过 API 配置/启动。
- 不引入私有仓库凭据或新的部署密钥。
- 不在设计文档评审前修改 parser、matcher、契约或前端代码。
