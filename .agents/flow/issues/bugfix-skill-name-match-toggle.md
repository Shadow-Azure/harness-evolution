# 新增进化对象成员开关：skill/agent 按名称匹配（默认关闭）

[English](bugfix-skill-name-match-toggle.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-73
milestone: bugfix
depends:
  - m13-01
  - m11-03
  - m11-04
priority: P2
status: in-progress
scope:
  - .agents/**
  - .env.example
  - apps/api/alembic/**
  - apps/api/app/api/**
  - apps/api/app/config.py
  - apps/api/app/db/**
  - apps/api/app/main.py
  - apps/api/app/service/evolution/**
  - apps/api/app/service/overview/**
  - apps/api/tests/**
  - apps/web/src/**
  - packages/contracts/**
  - docs/architecture.md
  - docs/architecture.en.md
  - docs/architecture.i18n.yaml
  - plans/**
  - plans/fullstack-design/05-api-design.md
  - plans/fullstack-design/06-database-design.md
  - plans/fullstack-design/07-backend-implementation.md
  - plans/fullstack-design/08-frontend-implementation.md
  - plans/ui-prototype-v2/**
  - tests/e2e/**
adr:
  - ../../notes/implemented/architecture/2026-11-27-member-name-match-switch.md
github:
  number: 648
  url: https://github.com/Shadow-Azure/harness-evolution/issues/648
```

## 背景

提出人 2026-11-27 补充诉求：Agent 和 Skill 的匹配都做成「子进化对象编辑框」里的开关，按进化对象成员粒度配置，而不是按 `.env` 部署粒度。原 issue 的两个环境变量方案（`HE_AGENT_MATCH_BY_NAME` / 拟新增的 `HE_SKILL_MATCH_BY_NAME`）作废，本 issue 改为成员级 `matchByName`；原型修改与 issue 更新已由 #651 合入，本实现 PR 交付数据库、API、匹配器、运行快照与前端开关。

当前匹配链路的关键事实：

- skill/agent 的版本身份是归一化定义正文的 body hash（`digest:<sha256(normalize_definition_body(body))>`），不是名称；目标版本解析和事件 `object_revision` 都围绕它（`target_content.py`、`acquisition/parsers/base.py`）。
- 总览的 `_analyse_target` 把 `condition.revision_candidates` 传给 `PotentialMatcher.associated_sessions`，按 `object_version`/`object_revision`/`definition_hash`/`document_revision` 过滤，因此同名但正文不同的 skill/agent 会被拆成多行，配置 ref 行可能显示 0 个 Session。
- 向导和启动目前不传 revision 过滤，按「对象类型 + 名称」关联；总览与向导/启动存在两套口径。
- 已实现的 `HE_AGENT_MATCH_BY_NAME` 只对 agent 生效，是部署级布尔量；同一台部署上的所有 agent 只能一起切换，同一配置里的多个 skill/agent 也无法分别选择。skill 仍走 hash 分支。
- 成员编辑框已经逐个编辑类型、名称、子目录；把一个 `matchByName` 开关放在成员行上，正好复用现有成员模型，不需要新增配置页或第二个总开关。

名称匹配会把「同名但正文不同」的对象归到同一对象，牺牲版本精确性，因此必须默认关闭、显式 opt-in。提出人最初所说的「md5sum」在代码里实际是 SHA-256 归一化 body hash；本 issue 沿用现有 `digest:` 身份，不引入新算法。

## 目标

- 在进化对象编辑框的每个成员行增加「名称匹配」开关，保存为成员字段 `matchByName`，布尔值，默认 `false`；只对 skill/agent 成员显示，knowledge 成员不显示。
- 关闭（默认）：该成员仍按定义正文摘要匹配；总览版本行、关联数、错误码和既有测试不变。
- 开启：只对该成员，Session 关联与总览版本行按「对象类型 + 名称」匹配，不再用 `definition_hash`/`object_revision` 过滤；该成员只显示一行配置版本（`defaultRef`），同名 Session 全部计入，历史报告按别名挂回该行。
- 同一个配置内不同成员可以分别开关：只开 skill 成员时 agent 成员保持摘要口径，反之亦然；多成员 `_merge_analyses` 的并集/去重不变。
- 删除 `HE_AGENT_MATCH_BY_NAME` 与 `skill_match_by_name` 的配置入口，不再新增环境变量；匹配模式随成员配置持久化，修改后不需要重启 `harness-api`。
- 报告内容身份、`targetRevision`、原文冻结、运行快照、缓存键与第 4 步统计仍使用 body hash；开关只改「关联与版本行」这层匹配。
- 更新 V2 原型和设计说明，并在本 issue 放入同一场景、同一视口、同一主题的 before/after 截图。
- 原型、设计说明和 issue 更新已由 #651 合入；本实现 PR 交付数据库、API、前端与匹配器。

## 设计依据

- [05 §4.20 自进化预览与启动（V2）](../../../plans/fullstack-design/05-api-design.md#420-自进化预览与启动v2)：`targetRevision` 只用于固定原文、报告和缓存范围，Session 关联按对象类型和名称的出现；本 issue 把该口径下沉到成员级开关。
- [05 §4.18 总览与空间 Session 列表（V2）](../../../plans/fullstack-design/05-api-design.md#418-总览与空间-session-列表v2)：对象卡版本身份与 `byVersion` 的契约；开关开启后该成员的版本键改为单个配置 ref。
- [06 §5.1 evolution_targets](../../../plans/fullstack-design/06-database-design.md#51-evolution_targets--可自进化的对象配置)：目标、成员与 `defaultRef` 字段；本 issue 在成员表增加一个布尔列，不在目标表增加部署级开关列。
- [06 §7.5 V2 口径](../../../plans/fullstack-design/06-database-design.md#75-v2-口径空间--触发点--潜在--归因三态)：对象出现与进入点、潜在与归因三态。
- [07 §5.12 潜在匹配](../../../plans/fullstack-design/07-backend-implementation.md#512-潜在匹配serviceevolutionpotentialpy)：`PotentialMatcher` 的查询与过滤位置；`MatchTarget` 需要携带每个成员自己的开关。
- [08 §9.5 进化对象配置页](../../../plans/fullstack-design/08-frontend-implementation.md#95-进化对象配置页evolutiontargets)：成员行编辑与提交；本 issue 在成员行增加开关，不新增独立页面。
- [V2 原型设计 §5.3](../../../plans/ui-prototype-v2/design-v2.md#53-双视角bad-case--进化对象)：成员行展示类型/名称/子目录，本 issue 增加「名称匹配」开关并给出前后截图。
- Agent Note [默认 body hash，显式开关放开 agent 名称匹配](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/architecture/2026-11-26-agent-name-match-switch.md)：上一版部署级开关的取舍；本 issue 把它替换为成员级配置，原开关退役。
- Agent Note [归因身份改为归一化 body hash 与后处理锚点](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/architecture/2026-11-18-body-hash-attribution-post-process.md)：body hash 身份与「未知不猜名称」的既有决策；成员级开关仍是有界、默认关闭的例外。

## 原型对照

同一 V2 原型、同一页面状态（`?u=admin&ws=ws-harness&page=overview&tab=targets`）、1500×1200 CSS 视口、2× DPR、浅色主题；数据为 `ws-harness` 合成 fixture。场景是新增进化对象弹窗，含一个 skill 成员和一个 agent 成员：基线只有类型/名称/子目录；变更后每个成员行增加「名称匹配」开关，截图示例中 skill 关闭、agent 开启，表示开关按成员独立。

| Before（`main` 原型，无开关） | After（#651 原型，成员行开关） |
| --- | --- |
| [![Before：成员行只有类型、名称、子目录](https://github.com/Shadow-Azure/harness-evolution/releases/download/skill-name-match-prototype-evidence-20261127/skill-name-match-before.png)](https://github.com/Shadow-Azure/harness-evolution/releases/download/skill-name-match-prototype-evidence-20261127/skill-name-match-before.png) | [![After：skill 关闭、agent 开启名称匹配](https://github.com/Shadow-Azure/harness-evolution/releases/download/skill-name-match-prototype-evidence-20261127/skill-name-match-after.png)](https://github.com/Shadow-Azure/harness-evolution/releases/download/skill-name-match-prototype-evidence-20261127/skill-name-match-after.png) |

两张图的页面、数据、弹窗结构、共享块和成员类型/名称/子目录一致；差异只在每个成员行末尾新增的「名称匹配」开关。

## 实现内容

### 原型与设计（#651 已合入）

- `plans/ui-prototype-v2/harness-evolution.html` 的 `v2TargetMemberRow` 增加 `matchByName` 参数和第 4 列开关；成员行网格改为 `类型 / 名称 / 子目录 / 名称匹配 / 移除`，开关沿用现有 `.switch` 视觉语言并缩小到成员行尺寸。
- `v2TargetModal` 用成员已有的 `matchByName` 渲染开关；`v2SaveTarget` 把 `matchByName` 写回成员对象；成员提示补充「各自决定是否按名称匹配」。
- `plans/ui-prototype-v2/design-v2.md §5.3` 记录成员级开关的默认值、开关语义和位置。
- 本 issue 放入 before/after 截图；原型 PR 不提交产品代码、数据库迁移或契约字段。

### 数据模型与契约

- 新增 Alembic 迁移（`0036_member_match_by_name.py`）：给 `evolution_target_members` 和 `evolution_run_targets` 各加 `match_by_name` 布尔列，`NOT NULL DEFAULT false`；不回填为 true。`evolution_targets` 不增加部署级列。
- 兼容没有成员行的历史目标：`member_objects` 合成成员时 `match_by_name=false`，行为与今天一致。
- 契约：`EvolutionTargetMemberWrite` 与 `EvolutionTargetMember` 增加 `matchByName: bool = false`；`EvolutionRunTarget` 快照增加同一字段；运行 `pnpm contract:generate` 更新 OpenAPI 与生成类型。
- 持久化：`EvolutionTargetMemberRecord`、`EvolutionRunTargetRecord`、repository 的 member load/write、`_member_rows`、run target 写入读取都带上该字段；创建/更新时保留每个成员自己的值。

### 匹配与总览

- `MatchTarget` 增加 `match_by_name: bool = False`；`MatchCondition` 始终携带成员级 `targets`。`PotentialMatcher.associated_sessions` 以每个目标的开关决定是否忽略 revision：开启时按对象类型 + 名称，关闭时保留现有 `observed_revisions` 过滤。
- 删除服务级 `agent_match_by_name` / `name_match_types` 与 `main.py` 的开关接线；`TargetOverviewService` 不再接收全局开关，改为在 `_member_target` 中从成员记录带入 `match_by_name`。
- `_analyse_target` 用 `target.match_by_name` 选择单版本行或现有 `_build_version_labels`；`_name_matched_version`、`_name_match_aliases` 改为类型无关，skill/agent 共用。
- 名称模式行的别名仍覆盖配置 ref、解析 revision、裸 body hash 和历史报告 `object_version`；`_newest_link_by_case` 按 case 取最新报告，保证 attributed/nonTarget 计数不归零。
- `launch.py`、`prepare.py`、`binding_worker.py` 构造 `MatchTarget` 时带上成员开关，并把开关写入 run 的成员快照；向导/启动当前不传 revision 过滤，仍按 presence 关联，本次不改变其默认行为，但快照和条件已携带开关，后续统一口径时不需要再改数据结构。
- knowledge 成员没有开关，`match_by_name` 固定 false；skill/agent 默认 false。

### 前端

- `apps/web/src/pages/evolution/targets/components/TargetFormDialog.vue` 的成员行增加 `el-switch`，标签「名称匹配」，仅 `objectType` 为 skill/agent 时显示；新建成员默认关闭，编辑回显已保存值。
- `apps/web/src/pages/evolution/targets/targetMembers.ts` 的 `TargetMember` 增加 `matchByName: boolean`；读取/回填/提交时保留该字段，旧响应缺字段按 false。
- 更新目标 API composable 与提交 payload、成员单测和表单测试；knowledge 成员不渲染开关。
- 不新增独立开关页、不把开关放到共享块、不改仓库/基线/测试工程字段的布局。

### 配置清理与文档

- `apps/api/app/config.py` 删除 `agent_match_by_name`；`.env.example` 删除 `HE_AGENT_MATCH_BY_NAME`，不新增 `HE_SKILL_MATCH_BY_NAME`；`main.py` 删除相关接线。
- 兼容说明：已经设置 `HE_AGENT_MATCH_BY_NAME=true` 的部署升级后默认全部成员关闭，需要按成员显式打开；不做自动回填，避免把同名不同正文的对象静默合并。部署文档和 release note 写明这一点。
- `docs/architecture.md` 与英文侧把「agent 名称匹配见 `HE_AGENT_MATCH_BY_NAME`」改为「skill/agent 成员可按 `matchByName` 显式按名称匹配，默认关闭，配置随成员持久化」；运行 `pnpm record:i18n -- docs/architecture.md` 重录配对。
- 05/06/07/08 设计说明更新成员字段、迁移、`MatchTarget` 与 MatchCondition、前端成员行和总览行为；新增 Agent Note 记录「成员级开关取代 env 开关」的取舍，并更新原 agent 开关 Note 为「已被成员级开关取代」；把新 Note 路径回填到 `adr`。

## 实施步骤

1. 原型与设计（#651 已合入）：改成员行开关、保存/回显、`design-v2.md §5.3`，在 issue 放入 before/after 截图；不提交产品实现。
2. 数据与契约：新增成员/运行快照的 `match_by_name` 迁移，更新 `EvolutionTargetMemberWrite/Read`、`EvolutionRunTarget` 和生成契约；补迁移与契约测试。
3. 持久化：members repository、目标创建/更新、run target 快照读写带上字段；补 repository/service 单测。
4. 匹配层：`MatchTarget.match_by_name`、`MatchCondition.targets`、matcher 的逐成员过滤；删除全局开关和 `main.py` 接线；补 skill/agent/混合成员/ knowledge 的匹配器单测。
5. 总览：`_member_target` 带入成员开关，`_analyse_target` 按成员选择单行/多行，名称模式别名和历史报告；补总览 API/单测。
6. 运行链路：launch/prepare/binding 的 `MatchTarget` 与 run 快照带上开关，保证配置变更后历史 run 仍按创建时口径回放。
7. 前端：成员行开关、`TargetMember` 类型、payload、表单与 API 测试；knowledge 不显示开关。
8. 清理 `HE_AGENT_MATCH_BY_NAME`、更新架构/设计与 Agent Note，跑 API/Web/契约/E2E 门禁，开实现 PR；PR 描述附开关关闭/开启的 before/after UI 截图和 env 迁移说明。

## 依赖与交付边界

- 依赖：m13-01（body hash 身份）、m11-03（总览 API）、m11-04（总览 UI）；三者均已 done。同仓多成员配置已由 m28-01 的成员模型承载，本 issue 只加成员字段，不改成员模型。
- 原型 PR（#651）交付边界：V2 原型、`design-v2.md`、本 issue 的正文与截图；不交付数据库迁移、API、前端表单、匹配器或 env 清理。
- 本实现 PR 交付边界：成员表/运行快照各一个布尔列、契约字段、成员表单开关、按成员的匹配分支；不改报告内容身份、`targetRevision`、缓存键、第 4 步统计、事件采集和解析算法。
- 名称匹配只在开关开启时生效；关闭时保持现有 body hash 口径。向导/启动当前 presence 关联的默认行为不在本 issue 改变。
- 不自动把历史数据回填为 true；需要名称匹配的成员由用户在新表单里显式开启。
- 本 issue 的 `adr` 在实现 PR 中回填新 Agent Note；原型 PR 不新增决策记录。

## 独立验证

原型 PR（#651，已合入）：

```sh
pnpm verify:flow
pnpm verify:flow -- --diff origin/main
pnpm lint:docs
pnpm verify:docs
```

- 原型：同一 fixture、同一 1500×1200 视口、2× DPR、浅色主题下，before 成员行没有开关，after skill/agent 两行各有一个「名称匹配」开关，示例中 skill 关闭、agent 开启；截图链接已写入 issue。
- 原型保存：在 after 原型里切换开关并点击保存，重新打开编辑弹窗能回显该成员的开关状态；knowledge 成员不显示开关。
- issue：正文已从 env 方案改为成员级 `matchByName`，包含数据/契约/匹配/前端/清理/验收；无残留「新增 `HE_SKILL_MATCH_BY_NAME`」表述。
- 流程与文档：`pnpm verify:flow`、`pnpm verify:flow -- --diff origin/main`、`pnpm lint:docs`、`pnpm verify:docs` 全绿。

本实现 PR：

```sh
pnpm test:api -- tests/bugfix-skill-name-match tests/m10-02-potential-matcher tests/m11-03-target-overview
pnpm test:web -- target
pnpm lint:api
pnpm typecheck:api
pnpm typecheck:web
pnpm contract:check
pnpm test:e2e -- --pattern "target"
pnpm verify:flow
pnpm verify:docs
```

- 迁移：旧成员/旧 run 的 `match_by_name` 均为 false；合成成员同样 false。
- API：成员写读回 `matchByName`，缺省 false；契约无手改。
- 匹配：只对开启成员忽略 revision；关闭成员仍按 hash；混合配置互不影响；knowledge 不参与。
- 运行：run 快照保留创建时开关，配置后改不影响历史回放。
- UI：同一 fixture、同一视口、同一主题下，成员开关关闭/开启的 before/after 截图附在实现 PR；knowledge 成员无开关。

## 验收标准

1. 原型成员行出现「名称匹配」开关，skill/agent 各自独立，默认关闭；knowledge 不显示；本 issue 有同一场景、同一视口、同一主题的 before/after 截图。
2. Issue 已改为成员级 `matchByName` 方案，明确删除 `HE_AGENT_MATCH_BY_NAME`、不再新增 `HE_SKILL_MATCH_BY_NAME`，并写明 env 迁移与默认 false 的影响。
3. 原型 PR 不包含产品实现（#651 已满足）；实现 PR 通过全部门禁。
4. 实现后：成员表与 run 快照持久化 `matchByName`，API 契约/生成类型同步；旧数据默认 false，合成成员 false。
5. 实现后：开关关闭的成员保持 body hash 匹配；开启的成员在总览与关联匹配中按名称，单行版本、历史报告别名与计数不归零；同配置其他成员不受影响。
6. 实现后：run 快照保留创建时开关；配置后改只影响后续匹配，不重写历史报告与 `targetRevision`。
7. 实现后：向导/启动的 presence 默认行为不变；报告缓存、第 4 步统计、事件采集与解析算法不变。
8. 实现后：前端成员表单可开关并回显，knowledge 不显示；`pnpm contract:check`、API/Web/E2E 门禁通过；UI 开关的 before/after 截图进入实现 PR 描述。
9. 常驻文档中英成对更新并重录配对；新 Agent Note 记录成员级开关决策并回填 `adr`。

## 门禁与 CI

- 原型 PR（#651）：`pnpm verify:flow`、`pnpm verify:flow -- --diff origin/main`、`pnpm lint:docs`、`pnpm verify:docs`；CI 的 docs-flow、flow-online 及其它 lane 全绿；不跑产品 API/Web 测试（无产品代码）。
- 实现 PR：API `pnpm lint:api`、`pnpm typecheck:api`、聚焦 `pnpm test:api -- tests/bugfix-skill-name-match tests/m10-02-potential-matcher tests/m11-03-target-overview`；Web `pnpm lint:web`、`pnpm typecheck:web`、`pnpm test:web`；契约 `pnpm contract:generate` / `pnpm contract:check`；迁移与 DB 测试；E2E 目标配置用例。
- 流程：提交与 PR 标题含 `(#N)`；本 issue 为 in-progress；`pnpm verify:flow` 与 `pnpm verify:flow -- --diff origin/main` 通过。
- UI 可见变化：实现 PR 必须附同一 fixture、同一视口、同一主题的成员开关关闭/开启 before/after 截图；#651 的原型截图只作为设计证据。
- Agent Note：实现 PR 新增成员级开关决策记录并回填 `adr`；不把运行日志、生产 Session 或凭据写入仓库。

## 非目标

- 原型 PR 不实现数据库迁移、API、前端或匹配器；本实现 PR 交付产品实现。
- 不保留或新增任何 `.env` 匹配开关；不做部署级默认值、环境变量兜底或自动回填。
- 不把报告内容身份、`targetRevision`、缓存键、原文冻结或第 4 步统计从 body hash 改成名称。
- 不改变向导/启动当前 presence 关联的默认行为；如后续要统一三处口径，另开 issue。
- 不改 knowledge 的匹配，也不做全局「名称优先、hash 兜底」的自动回退。
- 不改 `TargetContentResolver`/`TargetDefinitions` 的读取与报错行为，不用名称或默认分支猜测正文。
- 不迁移、不回填、不重算历史版本行与报告；不修改事件采集和解析算法；不新增独立开关页或第二套配置页。
