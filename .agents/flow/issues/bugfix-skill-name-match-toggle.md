# 新增 .env 开关：skill 进化对象按名称匹配（默认关闭，复用 agent 开关）

[English](bugfix-skill-name-match-toggle.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-69
milestone: bugfix
depends:
  - m13-01
  - m11-03
  - m11-04
priority: P2
status: ready
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
adr: []
github:
  number: 648
  url: https://github.com/Shadow-Azure/harness-evolution/issues/648
```

## 背景

提出人希望再增加一个 `.env` 匹配开关，默认关闭；开启后 skill 进化对象不再按定义正文摘要匹配，而是按「对象类型 + 名称」匹配。提出人明确要求复用已经实现的 agent 开关（`HE_AGENT_MATCH_BY_NAME`，issue #632 / PR #636），把 skill 与 agent 的名称匹配收成统一设计。

当前实现里，skill 与 agent 的版本身份都是归一化定义正文的 body hash，不是名称：

- 目标版本解析在选中 ref 下读取 `SKILL.md`，用 `definition_file_hash` 得到 `targetRevision=digest:<sha256(normalize_definition_body(body))>`（`apps/api/app/service/evolution/target_content.py`）；读取失败返回 `TARGET_CONTENT_UNRESOLVED`，不按名称回退。
- skill 触发事件的 `object_revision` 由 parser 用正文 hash 生成 `digest:<body hash>`（`apps/api/app/service/acquisition/parsers/base.py` 的 `_skill_revision`）；没有正文证据时才使用列表摘要兜底，`definition_hash` 是纯 body hash。
- 向导第 2/3 步、启动前的潜在检查本来就不传 `observed_revisions`，按「对象类型 + 名称」关联；总览的目标分析（对象列表、趋势、用例列表与详情共用 `_analyse_target`）把 `condition.revision_candidates` 传给 `PotentialMatcher.associated_sessions`，要求事件的 `object_version`/`object_revision`/`definition_hash`/`document_revision` 命中某个版本（`apps/api/app/service/overview/targets.py`、`apps/api/app/service/evolution/potential.py`）。
- 结果是同一个 skill 名称在总览里可能被拆成多行摘要：配置 ref 对应的版本行按 hash 过滤后为 0 个 Session，而同一名称在轨迹里明明存在；skill 正文变化后无法对齐。总览与向导两套口径也不一致。
- agent 开关已经只对 `object_type=agent` 生效，skill 仍走 hash 分支：匹配器用 `agent_match_by_name` 布尔量、总览用 `agent_match_by_name` 布尔量，两处由 `main.py` 分别传入；这是重复的类型判断，新增 skill 开关时正好收成一个按目标类型集合驱动的共享实现。

名称匹配会把「同名但正文不同」的 skill 归到同一对象，牺牲版本精确性。因此它必须是显式、可配置、默认关闭的例外；默认行为仍是 body hash，且「未知不猜名称」的既有决策不变。提出人所说的「md5sum」在代码里实际是 SHA-256 归一化 body hash，本 issue 按现有 `digest:` 身份描述，不引入新算法。

## 目标

- 新增可选环境变量 `HE_SKILL_MATCH_BY_NAME`，布尔值，默认 `false`；API 启动时读取，修改后需重启 `harness-api`。
- 关闭（默认）：skill 目标现有行为逐字不变，包括 body hash 身份、总览版本行、关联数、错误码与既有测试。
- 开启：只对 `object_type=skill` 的目标，Session 关联与总览版本行按「对象类型 + 名称」匹配，不再用 `definition_hash`/`object_revision` 过滤；一个 skill 目标只显示一行配置版本（目标的 `defaultRef`），同名 Session 全部计入。
- 开启时历史归因报告仍挂在这个 skill 的同一行下（按 case 取最新报告），不因版本折叠而消失或计数归零。
- 复用并统一 agent 开关的实现：配置层保留 `HE_AGENT_MATCH_BY_NAME` 的既有名称与语义，内部改为一个 `name_match_types` 集合，skill 与 agent 走同一条匹配与版本折叠代码路径；后续新增类型只需在配置层加入集合，不再复制布尔分支。
- 两个开关互不影响：只开 skill 时 agent 保持 hash 口径，只开 agent 时 skill 保持 hash 口径；knowledge 目标始终不受影响。
- 报告内容身份、`targetRevision`、原文冻结、运行快照、缓存键与第 4 步统计仍使用 body hash；开关只改「关联与版本行」这层匹配，不改报告正文与缓存范围。
- 事件采集、数据库结构、OpenAPI 契约、前端表单不变；历史 digest 版本和报告保留可读，不做回填或改写。

## 设计依据

- [05 §4.20 自进化预览与启动（V2）](../../../plans/fullstack-design/05-api-design.md#420-自进化预览与启动v2)：`targetRevision` 只用于固定原文、报告和缓存范围，Session 关联按对象类型和名称的出现；本 issue 把该口径从 agent 扩展到 skill，仍由显式开关控制。
- [05 §4.18 总览与空间 Session 列表（V2）](../../../plans/fullstack-design/05-api-design.md#418-总览与空间-session-列表v2)：对象卡版本身份与 `byVersion` 的契约；开关开启后对应类型的版本键改为单个配置 ref。
- [06 §5.1 evolution_targets](../../../plans/fullstack-design/06-database-design.md#51-evolution_targets--可自进化的对象配置)：目标类型、`defaultRef` 与绑定字段，两个开关都不新增列。
- [06 §7.5 V2 口径](../../../plans/fullstack-design/06-database-design.md#75-v2-口径空间--触发点--潜在--归因三态)：对象出现与进入点、潜在与归因三态。
- [07 §5.12 潜在匹配](../../../plans/fullstack-design/07-backend-implementation.md#512-潜在匹配serviceevolutionpotentialpy)：`PotentialMatcher` 的查询与过滤位置，skill 与 agent 共用同一条关联路径。
- [08 §9.5 进化对象配置页](../../../plans/fullstack-design/08-frontend-implementation.md#95-进化对象配置页evolutiontargets)：对象版本与总览展示入口，本 issue 不新增表单字段。
- Agent Note [默认 body hash，显式开关放开 agent 名称匹配](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/architecture/2026-11-26-agent-name-match-switch.md)：agent 开关的既有取舍与「只改关联和版本行、不改报告身份」边界，本 issue 把它统一为按类型集合。
- Agent Note [归因身份改为归一化 body hash 与后处理锚点](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/architecture/2026-11-18-body-hash-attribution-post-process.md)：body hash 身份的决策与当时拒绝只按名称匹配的理由；本开关仍是有界、默认关闭的例外。

## 实现内容

### 配置

- `apps/api/app/config.py` 的 `Settings` 增加 `skill_match_by_name: bool = False`，随 `HE_` 前缀读取；保留 `agent_match_by_name: bool = False` 的名称、默认值和语义不变。
- 在 `Settings` 上增加只读派生属性 `name_match_types`，返回当前启用的目标类型集合（`agent_match_by_name` 为真时含 `agent`，`skill_match_by_name` 为真时含 `skill`，knowledge 永不加入）。非法布尔值仍由 Pydantic 在启动时拒绝。
- `.env.example` 在 `HE_AGENT_MATCH_BY_NAME` 旁增加 `# HE_SKILL_MATCH_BY_NAME=false`，说明「仅影响 skill 目标的关联与总览版本行；默认关闭；报告、缓存与 targetRevision 仍按 body hash；改后重启 `harness-api`」。
- 不新增第三个「总开关」；运维接口仍是两个独立布尔项，统一发生在代码内部，避免给已经部署的 `HE_AGENT_MATCH_BY_NAME` 改名或引入静默失效。

### 共享类型集合

- `PotentialMatcher` 的构造参数由 `agent_match_by_name: bool = False` 改为 `name_match_types: frozenset[str] = frozenset()`；默认空集合，其他调用方无需感知。
- `TargetOverviewService` 的构造参数同步改为 `name_match_types: frozenset[str] = frozenset()`；`main.py` 的三处构造（预览匹配器、常驻匹配器、总览服务）统一传 `resolved_settings.name_match_types`。
- `PotentialMatcher.associated_sessions` 的过滤分支改为 `ignore_revisions = event.object_type in self._name_match_types`；skill 与 agent 不再各持布尔量，knowledge 不在集合中所以行为不变。
- `TargetOverviewService._analyse_target` 的判定改为 `name_matched = target.object_type in self._name_match_types`。
- 把 agent 专用命名改为类型无关：`_agent_name_aliases` → `_name_match_aliases`，`_name_matched_version`、`_name_match_commit`、`match_by_name` 参数的注释与 docstring 明确同时服务 skill/agent；不改变算法。
- 更新单测里 `agent_match_by_name=True` 的构造方式为 `name_match_types=frozenset({"agent"})`，避免测试继续固化旧布尔接口。

### 匹配与总览

- 开关开启且目标是 skill 时，`TargetOverviewService` 复用现有 `_name_matched_version`：只构造一个以 `defaultRef` 为键的版本行，仍解析 `SKILL.md` 以得到 ref/revision/commit 供展示；解析失败只影响 commit，不阻止名称关联。
- 该行的别名集合覆盖配置 ref、解析出的 revision、裸 body hash 以及该对象历史报告的 `object_version`；`_newest_link_by_case` 继续按 case 取最新报告，保证既有 attributed/nonTarget 计数不因版本折叠而归零。
- `PotentialMatcher` 在开关开启且事件类型是 skill 时忽略传入的 `observed_revisions`，按「对象类型 + 名称」关联窗口内全部同名 Session；事件版本仍原样保留为证据，但不参与入选。
- 多成员配置：`_analyse_config` 已按成员调用 `_analyse_target`，因此开关按成员类型生效；只开 skill 时，配置里的 skill 成员折叠为一行，agent 成员仍显示 digest 版本行，`_merge_analyses` 的并集/去重不变。
- 向导第 2/3 步与启动前潜在检查本来就不按 revision 过滤，补一条「两个开关开启时行为与默认一致」的回归断言；启动、报告、缓存仍走 `targetRevision`，不做名称回退。
- skill 与 knowledge 目标默认路径不变；两个开关都关闭时，`_build_version_labels` 生成的版本行、统计与错误码逐字不变。

### 文档与决策

- `docs/architecture.md` 与英文侧的「未知不猜名称」改为：skill/agent 名称匹配分别由 `HE_SKILL_MATCH_BY_NAME` / `HE_AGENT_MATCH_BY_NAME` 控制，默认关闭；运行 `pnpm record:i18n -- docs/architecture.md` 重录配对。
- 05/06/07/08 设计说明把只提 `HE_AGENT_MATCH_BY_NAME` 的段落扩为两个开关，并明确「各自只影响本类型的关联与总览版本行，报告与缓存仍按 body hash」。
- 新增 Agent Note（`implemented/architecture`），记录「两个布尔开关、一个内部类型集合」的统一取舍、对同名不同正文精度的影响，以及为什么不用单一列表型环境变量替换既有部署；同时更新既有 agent 开关 Note 中「skill 不受影响」的表述为「只开 agent 开关时 skill 不受影响」，避免与新增开关矛盾。
- 把新增 Agent Note 路径回填到本 issue 的 `adr`。

## 实施步骤

1. 在 `Settings` 落 `skill_match_by_name` 与 `name_match_types` 派生属性，补未设置、false、true、双开关、非法值的配置单测，同步 `.env.example`。
2. 把 `PotentialMatcher` 与 `TargetOverviewService` 的布尔参数统一成 `name_match_types`，改 `main.py` 三处接线；补 skill/agent/双开关/knowledge 的匹配器单测，确认 agent 既有断言不变。
3. 复用 `_name_matched_version` 与别名逻辑到 skill，补总览 API/单测：默认多行 digest 行为不变；只开 skill 时 skill 单行、纳入同名不同 hash 的 Session、历史报告计数不归零；只开 agent 时 skill 不变；双开关与混合成员配置分别验证。
4. 更新 `docs/architecture` 中英与 05/06/07/08 设计说明，新增 Agent Note 并回填 `adr`，运行文档配对与流程门禁。
5. 用同一 fixture、同一视口、同一主题分别在两个开关关闭/仅 skill 开启时调用总览详情并截取 before/after，记录 skill 版本行数、关联 Session 数与历史报告挂载。
6. 跑本 issue 的验证命令，提交、开 PR，PR 描述写明默认关闭的兼容性证据、skill 开关前后对比与限制。

## 依赖与交付边界

- 依赖：m13-01（body hash 身份）、m11-03（总览 API）、m11-04（总览 UI）；三者均已 done。
- 与同仓多成员配置兼容：开关按成员 `object_type` 生效，不做配置级一刀切；本 issue 不修改成员模型。
- 交付边界：一处环境变量、配置层的类型集合、共享匹配器的过滤条件、总览版本聚合与历史报告别名；不改数据库结构、不改 OpenAPI、不改事件写入、不改 target/run 的 `targetRevision`、报告缓存键或第 4 步统计口径。
- 不改 `TargetContentResolver`/`TargetDefinitions`：skill 的 `SKILL.md` 仍是启动与归因的必需内容，读取失败仍显式报错，不用名称猜测正文。
- 不修改历史行、不做迁移回填、不重算历史报告；任一开关可随时改回，改回后恢复 hash 口径。

## 独立验证

```sh
pnpm test:api -- tests/bugfix-skill-name-match tests/bugfix-agent-name-match tests/m10-02-potential-matcher tests/m11-03-target-overview
pnpm lint:api
pnpm typecheck:api
pnpm contract:check
pnpm verify:flow
pnpm verify:docs
```

- 配置单测：未设置/false 时 `name_match_types` 为空；只设 `HE_SKILL_MATCH_BY_NAME=true` 时为 `{"skill"}`；只设 agent 时为 `{"agent"}`；两个都开时两者都在；非法值在启动校验时报错。
- 匹配器单测：skill 开关开启时忽略 skill 的 `observed_revisions`，同名不同 `definition_hash` 的 Session 计入；agent 开关关闭时 agent 仍按 hash；knowledge 不受任一开关影响。
- 总览单测：默认时 skill 仍显示现有 digest 版本行；只开 skill 时 skill 目标只有一行 `defaultRef`，同名不同 hash 的 Session 与历史报告都计入且计数不归零；只开 agent 时 skill 断言不变；双开关与混合成员配置各自独立。
- 文档门禁：`docs/architecture` 中英配对重录，`pnpm verify:docs` 与 `pnpm verify:flow` 全绿；Agent Note 与 `adr` 回填。
- 浏览器核对：同一 fixture、同一视口与主题下，默认显示 skill digest 版本行，仅开 skill 后只显示配置 ref 一行；截图随 PR 描述提交。

## 验收标准

1. 不设置 `HE_SKILL_MATCH_BY_NAME` 或设为 `false` 时，skill 的关联数、总览版本行、第 4 步统计、错误码与当前逐字一致，既有测试无需改断言。
2. 设置 `HE_SKILL_MATCH_BY_NAME=true` 并重启后，skill 目标详情只有一行配置版本；同名 Session 即使 `definition_hash` 与目标 body hash 不同也计入，不再出现同名摘要多行。
3. 只开 skill 时 agent 目标行为不变；只开 `HE_AGENT_MATCH_BY_NAME` 时 skill 目标行为不变；两个都开时各自折叠；knowledge 目标始终不变。
4. 开关开启时历史报告仍按 case 挂到唯一版本行，attributed/nonTarget 计数不因版本折叠或别名缺失归零；第 4 步 `reused/fresh` 与 `nonTargetKnown` 仍由 body hash 报告范围决定，报告正文、`targetRevision` 与运行快照不被改写。
5. 同仓多成员配置中，开关只折叠已启用类型的成员，其他成员保留 digest 版本行，合并后的 Session 与 case 并集不丢失。
6. 开启时总览仍尝试解析 `SKILL.md` 以显示 ref/commit；解析失败时总览可按名称关联，但启动仍返回现有 `TARGET_CONTENT_UNRESOLVED`，名称匹配不会绕过内容读取。
7. 关闭开关后恢复原 hash 口径；历史 digest 版本与报告仍可读取，不需要数据迁移。
8. 常驻文档中英成对更新并重录配对；新增 Agent Note 记录统一取舍并回填 `adr`；`pnpm verify:flow` 与 `pnpm verify:docs` 通过。

## 门禁与 CI

- API：`pnpm lint:api`、`pnpm typecheck:api`、`pnpm test:api -- tests/bugfix-skill-name-match tests/bugfix-agent-name-match tests/m10-02-potential-matcher tests/m11-03-target-overview`。
- 契约：不改 API 字段时 `pnpm contract:check` 无 diff；若实现意外改到 DTO，必须先更新 05 设计并重新生成。
- 文档：`pnpm lint:docs`、`pnpm verify:docs`；`docs/architecture` 中英改动后运行 `pnpm record:i18n -- docs/architecture.md`。
- 流程：提交与 PR 标题含 `(#N)`，本 issue 状态为 in-progress 后再开实现 PR；`pnpm verify:flow` 与 `pnpm verify:flow -- --diff origin/main` 通过。
- UI 可见变化：PR 描述附同一 fixture、同一视口、同一主题的 before/after 截图，明确基线为两个开关关闭、变更为仅 skill 开启；只给 after 不算完成。
- Agent Note：新增决策记录并在本 issue `adr` 回填；不把运行日志、生产 Session 或凭据写入仓库。

## 非目标

- 不把 skill 的 `targetRevision`、报告缓存键、原文冻结或第 4 步统计从 body hash 改成名称；同名不同正文的报告仍需按内容区分。
- 不改 `TargetContentResolver`/`TargetDefinitions` 的读取与报错行为，不用名称或默认分支猜测正文。
- 不改 knowledge 的匹配，也不做全局「名称优先、hash 兜底」的自动回退。
- 不给 agent 开关改名、不把两个布尔项替换成单一列表型环境变量；本 issue 只统一内部代码路径，运维接口保持向后兼容。
- 不加 UI 开关、表单字段或契约字段；不改部署流水线注入，生产通过服务器 `.env` 配置并重启。
- 不迁移、不回填、不重算历史版本行与报告，不修改事件采集和解析算法。
