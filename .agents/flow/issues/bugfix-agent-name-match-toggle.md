# 新增 .env 开关：agent 进化对象按名称匹配（默认关闭）

[English](bugfix-agent-name-match-toggle.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-67
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
  - apps/api/app/config.py
  - apps/api/app/main.py
  - apps/api/app/service/evolution/**
  - apps/api/app/service/overview/**
  - apps/api/tests/**
  - docs/architecture.md
  - docs/architecture.en.md
  - docs/architecture.i18n.yaml
  - plans/fullstack-design/05-api-design.md
  - plans/fullstack-design/06-database-design.md
  - plans/fullstack-design/07-backend-implementation.md
  - plans/fullstack-design/08-frontend-implementation.md
  - plans/2026-11-26-pr636-review.md
adr:
  - ../../notes/implemented/architecture/2026-11-26-agent-name-match-switch.md
github:
  number: 632
  url: https://github.com/Shadow-Azure/harness-evolution/issues/632
```

## 背景

提出人希望增加一个 `.env` 匹配开关，默认关闭；开启后 agent 进化对象不再按定义正文的摘要匹配，而是按名称匹配。当前实现里 agent 的身份确实是「定义正文的归一化 body hash」而不是名称，但并非所有读取路径都按它过滤：

- 目标版本解析在选中 ref 下读取 `AGENT.md`/`agent.md`，用 frontmatter-aware 的 `definition_file_hash` 得到 `targetRevision=digest:<sha256(normalize_definition_body(body))>`（`apps/api/app/service/evolution/target_content.py`）；读取失败返回 `TARGET_CONTENT_UNRESOLVED`，不按名称回退。
- agent 触发事件的 `object_revision` 是 `digest:sha256(agentType + builtin 标记 + body hash)` 的组合摘要（`apps/api/app/service/acquisition/parsers/base.py` 的 `_agent_revision`），不是目标解析出的纯 body hash；`definition_hash` 才是纯 body hash。
- 向导第 2/3 步、启动前的潜在检查和后台绑定调用 `PotentialMatcher.associated_sessions` 时不传 `observed_revisions`，已经按「对象类型 + 名称出现」关联；总览的目标分析（右侧目标列表、趋势、用例列表与详情共用 `_analyse_target`）把 `condition.revision_candidates` 传进去（`apps/api/app/service/overview/targets.py`），要求事件的 `object_revision`/`definition_hash` 命中该版本的 hash。
- 启动的 latest-reports 缓存门、第 4 步的复用/非该对象统计和后台绑定去重仍按 `targetRevision` 查询（`launch.py` 的 `latest_reports` 门、`potential.py` 的绑定包预览分支、`binding_worker.py` 的完成去重）；它们属于报告/缓存范围，不属于本开关的关联匹配层。
- 结果是同一个 agent 名称在总览里可能被拆成多行摘要：配置 ref 对应的版本行按 hash 过滤后为 0 个 Session，而同一名称在轨迹里明明存在；agent 正文在不同版本、不同轨迹快照或运行时注入之间变化时无法对齐。总览版本行和向导关联两套口径也不一致。

名称匹配会把「同名但正文不同」的 agent 归到同一对象，牺牲版本精确性。因此它必须是显式、可配置、默认关闭的例外；默认行为仍是 body hash，且「未知不猜名称」的既有决策不变。

## 目标

- 新增可选环境变量 `HE_AGENT_MATCH_BY_NAME`，布尔值，默认 `false`；API 启动时读取，修改后需重启 `harness-api`。
- 关闭（默认）：现有行为逐字不变，包括 body hash 身份、总览版本行、错误码与既有测试。
- 开启：只对 `object_type=agent` 的目标，Session 关联与总览版本行按「对象类型 + 名称」匹配，不再用 `definition_hash`/`object_revision` 过滤；一个 agent 目标只显示一行配置版本（目标 `defaultRef`），同名 Session 全部计入。
- 开启时历史归因报告仍挂在这个 agent 的同一行下（按 case 取最新报告），不因版本折叠而消失或计数归零。
- 报告内容身份、`targetRevision`、原文冻结、运行快照、缓存键与第 4 步统计仍使用 body hash；开关只改「关联与版本行」这层匹配，不改报告正文与缓存范围。
- skill 与 knowledge 目标不受影响；事件采集、数据库结构、OpenAPI 契约不变。
- 历史 digest 版本和报告保留可读，不做回填或改写。

## 设计依据

- [05 §4.20 自进化预览与启动（V2）](../../../plans/fullstack-design/05-api-design.md#420-自进化预览与启动v2)：`targetRevision` 只用于固定原文、报告和缓存范围，Session 关联按对象类型和名称的出现；本开关把该口径显式扩展到仍按 hash 过滤的总览版本行。
- [05 §4.18 总览与空间 Session 列表（V2）](../../../plans/fullstack-design/05-api-design.md#418-总览与空间-session-列表v2)：对象卡版本身份与 `byVersion` 的契约，开关开启后 agent 的版本键改为单个配置 ref。
- [06 §5.1 evolution_targets](../../../plans/fullstack-design/06-database-design.md#51-evolution_targets--可自进化的对象配置)：目标类型、`defaultRef` 与绑定字段，开关不新增列。
- [06 §7.5 V2 口径](../../../plans/fullstack-design/06-database-design.md#75-v2-口径空间--触发点--潜在--归因三态)：对象出现与进入点、潜在与归因三态。
- [07 §5.12 潜在匹配](../../../plans/fullstack-design/07-backend-implementation.md#512-潜在匹配serviceevolutionpotentialpy)：`PotentialMatcher` 的查询与过滤位置。
- [08 §9.5 进化对象配置页](../../../plans/fullstack-design/08-frontend-implementation.md#95-进化对象配置页evolutiontargets)：对象版本与总览展示入口，本 issue 不新增表单字段。
- Agent Note [归因身份改为归一化 body hash 与后处理锚点](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/architecture/2026-11-18-body-hash-attribution-post-process.md) 与 [Claude 子 agent prompt 解析](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/bug-fix/2026-11-21-claude-attachment-prompt-snapshot.md)：body hash 身份的决策与当时拒绝只按名称匹配的理由；本开关是有界、默认关闭的例外。

## 实现内容

### 配置

- `apps/api/app/config.py` 的 `Settings` 增加 `agent_match_by_name: bool = False`，随 `HE_` 前缀读取；非法布尔值按 Pydantic 既有校验在启动时失败。
- `.env.example` 在归因/自进化可选配置组（`HE_ATTRIBUTION_*` 附近）增加 `# HE_AGENT_MATCH_BY_NAME=false`，说明「仅影响 agent 目标的关联与总览版本行；默认关闭；改后重启 `harness-api`」。

### 共享匹配器

- `PotentialMatcher` 增加构造参数 `agent_match_by_name`（默认 `False`），`apps/api/app/main.py` 的两处构造都传入 `resolved_settings.agent_match_by_name`。
- `associated_sessions` 在「开关开启且 `condition.target_type == "agent"`」时忽略传入的 `observed_revisions`，其余分支、计数与排序不变。
- 向导第 2/3 步与启动前的潜在检查本来就不按 revision 过滤，无需改代码，但补一条「开关开启时行为完全相同」的回归断言。
- `latest_reports`、`count_non_target_cases`、第 4 步绑定包预览与 `BindingWorker` 的完成去重保持现状（报告范围仍按 `targetRevision`），不在本开关的改动范围。

### 总览对象详情

- `TargetOverviewService` 增加同一开关；开关开启且目标是 agent 时，不用 `_build_version_labels` 从事件 `object_revision` 累积摘要版本，而是构造单个规范版本：键为目标的 `defaultRef`，显示为配置 ref。
- 该版本不传 `observed_revisions`，按名称关联窗口内所有含该 agent 的 Session；事件版本仍原样保留为证据，但不参与入选。
- 历史报告仍要挂到这一行，但 `_newest_link_by_case` 按 `object_version` 是否落在 label aliases 里选报告；单 ref 版本没有历史 digest 别名。名称模式必须为该行构造别名集合（配置 ref、解析 revision、裸 hash，以及该对象历史报告的 `object_version`），或等价地按 case 取该对象最新报告，保证既有 attributed/nonTarget 计数不归零。不能只依赖 `list_attributions` 的对象过滤。
- `byVersion` 只有一行，响应字段不增不减；历史 digest 版本作为别名参与报告匹配，不作为独立版本行显示。
- 版本内容解析仍用于显示 ref/commit 与启动链路；解析失败不再让版本行变成「未解析 0 关联」，匹配仍按名称给出 Session。启动仍需要内容解析，失败继续返回现有 `TARGET_CONTENT_UNRESOLVED`。
- skill/knowledge 目标保持现有 `_build_version_labels` 路径，开关对它们为空操作。

### 文档与决策

- `docs/architecture.md` 与英文侧的「未知不猜名称」补一句：agent 名称匹配是 `HE_AGENT_MATCH_BY_NAME` 控制的显式例外，默认关闭。
- 05/06/07/08 设计说明补开关条件语义：默认 hash；开启时 agent 关联/版本行按名称，报告与缓存仍按 body hash。
- 新增 Agent Note（`implemented/architecture` 或 `implemented/feature`），记录「默认 hash、显式开关放开 agent 名称匹配」的取舍与「不修改报告内容身份」的边界，并把路径回填到本 issue 的 `adr`。

## 实施步骤

1. 在 `Settings` 落字段与单测（未设置、false、true、非法值），同步 `.env.example`。
2. 给 `PotentialMatcher` 加开关，改 `associated_sessions` 的过滤分支，补匹配器单测。
3. 改 `TargetOverviewService` 的 agent 名称模式版本构建、关联与历史报告别名，补总览 API/单测：开关关闭时保持现有 digest 版本行；开启时只有一行、纳入 hash 不匹配的同名 Session，且既有报告的 attributed/nonTarget 计数不归零。
4. 更新 `docs/architecture` 中英与 05/06/07/08 设计说明，新增 Agent Note，运行文档与配对门禁。
5. 用 fixture 在本地 API 上分别以开关关闭/开启调用总览详情，记录版本行数、关联 Session 数、历史报告挂载与 `byVersion`；如涉及浏览器展示，附同 fixture、同视口、同主题的开关前后截图。
6. 跑本 issue 的验证命令，提交、开 PR，PR 描述写明默认关闭的兼容性证据与开关开启的行为对比。

## 依赖与交付边界

- 依赖：m13-01（body hash 身份）、m11-03（总览 API）、m11-04（总览 UI）；三者均已 done。
- 交付边界：一处环境变量、共享匹配器的过滤条件、总览版本聚合与历史报告别名；不改数据库结构、不改 OpenAPI、不改事件写入、不改 target/run 的 `targetRevision`、报告缓存键或第 4 步统计口径。
- 不改 `TargetContentResolver`/`TargetDefinitions`：agent 的 `AGENT.md` 仍是启动与归因的必需内容，读取失败仍显式报错，不用名称猜测正文。
- 不修改历史行、不做迁移回填、不重算历史报告；开关可随时改回，改回后恢复 hash 口径。

## 独立验证

```sh
pnpm test:api -- tests/m11-03-target-overview tests/m10-02-potential-matcher tests/m13-01-body-hash-attribution
pnpm lint:api
pnpm typecheck:api
pnpm verify:flow
pnpm verify:docs
```

- 配置单测：未设置/false 为关闭；true 为开启；非法值在启动校验时报错。
- 匹配器与总览单测：关闭时既有 digest 版本行与关联数不变；开启时 agent 目标只有一行、纳入定义 hash 不同的同名 Session；skill 目标在开启时仍按 digest 版本行。
- 总览报告：开关开启时，带历史 digest 报告的 case 仍挂在唯一版本行并被计入，不因别名缺失归零；同名 Session 扩大后计数可以增加，但不能丢掉这些历史报告。
- 文档门禁：`docs/architecture` 中英配对重录，`pnpm verify:docs` 与 `pnpm verify:flow` 全绿。
- 浏览器核对：同一 fixture、同一视口与主题下，开关关闭显示现有 digest 版本行，开启只显示配置 ref 一行；截图随 PR 描述提交。

## 验收标准

1. 不设置 `HE_AGENT_MATCH_BY_NAME` 或设为 `false` 时，总览版本行、关联数、第 4 步统计、错误码与当前逐字一致，既有测试无需改断言。
2. 设置 `HE_AGENT_MATCH_BY_NAME=true` 并重启后，agent 目标详情只有一行配置版本；同名 Session 即使 `definition_hash` 与目标 body hash 不同也计入，不再出现同名摘要多行。
3. 同一开关下 skill 与 knowledge 目标行为不变；混合空间（skill + agent 目标）互不影响。
4. 开关开启时历史报告仍按 case 挂到唯一版本行，attributed/nonTarget 计数不因版本折叠或别名缺失归零；第 4 步 `reused/fresh` 与 `nonTargetKnown` 仍由 body hash 报告范围决定，报告正文、`targetRevision` 与运行快照不被改写。
5. 关闭开关后恢复原 hash 口径；历史 digest 版本与报告仍可读取，不需要数据迁移。
6. `AGENT.md` 缺失或读不到时，启动/归因仍返回现有 `TARGET_CONTENT_UNRESOLVED`，名称匹配不会绕过内容读取。
7. 常驻文档中英成对更新并重录配对；Agent Note 记录开关取舍，`adr` 回填。

## 门禁与 CI

- API：`pnpm lint:api`、`pnpm typecheck:api`、`pnpm test:api -- tests/m11-03-target-overview tests/m10-02-potential-matcher tests/m13-01-body-hash-attribution`。
- 契约：不改 API 字段时 `pnpm contract:check` 无 diff；若实现意外改到 DTO，必须先更新 05 设计并重新生成。
- 文档：`pnpm lint:docs`、`pnpm verify:docs`；`docs/architecture` 中英改动后运行 `pnpm record:i18n -- docs/architecture.md`。
- 流程：提交与 PR 标题含 `(#N)`，本 issue 状态为 in-progress 后再开实现 PR；`pnpm verify:flow` 与 `pnpm verify:flow -- --diff origin/main` 通过。
- UI 可见变化：PR 描述附开关关闭/开启的同 fixture、同视口、同主题 before/after 截图；只给 after 不算完成。

## 非目标

- 不把 agent 的 `targetRevision`、报告缓存键、原文冻结或第 4 步统计从 body hash 改成名称；同名不同正文的报告仍需按内容区分。
- 不改 `TargetContentResolver`/`TargetDefinitions` 的读取与报错行为，不用名称或默认分支猜测正文。
- 不改 skill 与 knowledge 的匹配；不做全局「名称优先、hash 兜底」的自动回退；不改 `latest_reports`、`count_non_target_cases` 与后台绑定去重的 scope。
- 不加 UI 开关、表单字段或契约字段；不改部署流水线注入，生产通过服务器 `.env` 配置并重启。
- 不迁移、不回填、不重算历史版本行与报告。
