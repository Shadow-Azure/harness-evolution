# 18 同仓多成员进化对象

> 状态：设计已确认，待 m28-01 实现。本文是「一条配置 = 一个进化对象（含多个成员）」的前后端设计权威；原型见 [ui-prototype-v2/harness-evolution.html](../ui-prototype-v2/harness-evolution.html)，前后截图在本地 `plans/ui-prototype-v2/evidence/multi-object-target/`（不入库）。
>
> 关联：[06 数据库表结构设计](06-database-design.md)、[05 后端接口设计](05-api-design.md)、[07 后端实现设计](07-backend-implementation.md)、[08 前端实现设计](08-frontend-implementation.md)、[roadmap](../../.agents/flow/roadmap.md) 的 m28。

## 1. 背景与决策

### 1.1 诉求

同一个代码仓里常同时存在多个 skill 和 agent（例如 `skills/deep-research` 与 `skills/code-review`），它们共享仓库、基线与评测工程，bad case 也经常来自同一批 Session。用户希望把这一组对象作为一个**进化对象**配置和进化：

- 配置一次：仓库、基线、验证集/测试集测试工程 ID、主指标、归因 Skill 只填一次。
- 成员逐个列：每个成员有类型、名称、子目录，各自冻结定义、各自关联 bad case。
- 一次 run 一起进化：共享同一个基线 commit，patch 范围覆盖全部成员目录，评测一次提交全部成员资产。
- 总览按这条配置看整体潜在 bad case，成员作为明细。

### 1.2 现状与缺口

今天的 `evolution_targets` 一行就是一个对象：唯一约束是 `(workspace_id, object_type, object_name)`，作用域 `sub_dir`、测试工程与绑定归因都挂在行上。同仓两个 skill 只能建两条配置，于是：

- 仓库、基线、测试工程、归因 Skill 要重复填 N 次；
- bad case 归属分散在 N 条配置，无法作为一个进化对象统一筛选与归因；
- 一次 run 只能针对一个对象，无法利用"这些 case 往往同时涉及多个对象"的事实；
- 评测与 patch 都只覆盖一个目录。

### 1.3 决策

一条 `evolution_targets` = 一个进化对象；新增 `evolution_target_members` 承载成员。共享字段留在配置行，成员字段迁到成员行：

| 字段 | 归属 | 理由 |
|---|---|---|
| `repo_url` | 共享 | 一个 run 只 clone 一次、只有一个 `base_commit` |
| `default_ref` | 共享 | 成员必须同 ref，否则基线 commit 不唯一 |
| `validation_project_id` / `test_project_id` / `primary_metric_key` | 共享 | 评测平台一次 launch 只认一个模板；多资产是同一模板下的资产覆盖，指标只有一个 |
| `attribution_package_id` 与绑定快照 | 共享 | 后台归因是"这条配置的绑定" |
| `object_type` / `object_name` / `sub_dir` | 成员 | bad case、Session 关联、归因报告都以对象名称为键；patch 与评测资产按目录 |
| 定义冻结（commit / digest / 原文） | 成员 | 每个成员一个 `SKILL.md` / `AGENT.md`，digest 逐成员参与缓存键 |

两条硬约束：

- **成员必须同仓**。跨仓成员需要多仓 run 模型，本设计不做。
- **同一成员只能属于一条配置**。否则 bad case 与归因报告会歧义；保存时全局校验。

### 1.4 放弃的方案

- **每个成员一条配置 + 向导多选**：配置重复、bad case 归属分散、向导被迫引入"主对象"概念；用户已否决该交互。
- **只做批量填表、run 仍单对象**：解决不了"一起进化"，等于没解决核心诉求。
- **把成员做成 JSON 列**：无法对成员做唯一约束与按成员 join 查询，绑定与总览都要拆 JSON，不采用。

### 1.5 外部契约核对

评测平台（`ai-eval-platform@main d5231fe`）已核实：`asset_override.asset_paths` 是 `list[str]`、无数量上限、单路径 ≤500 字符、整字段替换；一次 launch 共用一个 `commit`，`asset.resolved_commit` 单值；任一路径缺失整单 422。测试工程与主指标因此必须共享，与本文决策一致。

## 2. 领域模型

```text
workspace
  └── evolution_targets（1 行 = 1 个进化对象）
        ├── repo_url / default_ref / validation_project_id / test_project_id
        │   / primary_metric_key / attribution_package_id / enabled
        └── evolution_target_members（N 行）
              └── object_type / object_name / sub_dir / definition{commit,digest,preview}

evolution_runs（1 行 = 1 次运行）
  ├── target_config_id → evolution_targets.id
  ├── 旧列：target_type / target_name / target_version / target_revision / repo_url / sub_dir
  │   （兼容窗口内写首个成员）
  └── evolution_run_targets（N 行 = 本次运行的成员快照）
        └── object_type / object_name / target_version / target_revision / sub_dir / base_commit
```

对象身份的查找规则：

- 按配置启动：`targetId` → 配置 + 成员。
- 按对象反查（从 bad case 启动、V1 读端点）：`(workspace, object_type, object_name)` → 成员 → 配置。命中多条配置时返回 409，要求先合并配置。

## 3. 数据模型

### 3.1 新表

```sql
evolution_target_members
  id             VARCHAR(36) PK
  target_id      VARCHAR(36) NOT NULL FK evolution_targets(id) ON DELETE CASCADE
  seq            INT NOT NULL
  object_type    VARCHAR(16) NOT NULL      -- skill | agent
  object_name    VARCHAR(128) NOT NULL
  sub_dir        VARCHAR(512) NOT NULL
  definition     JSON NULL                 -- {commit, digest, key, path, preview}
  created_at     TIMESTAMP NOT NULL
  UNIQUE (target_id, object_type, object_name)
  UNIQUE (target_id, seq)
  INDEX  (object_type, object_name)

evolution_run_targets
  id               VARCHAR(36) PK
  run_id           VARCHAR(36) NOT NULL FK evolution_runs(id) ON DELETE CASCADE
  seq              INT NOT NULL
  target_config_id VARCHAR(36) NULL FK evolution_targets(id) ON DELETE SET NULL
  member_id        VARCHAR(36) NULL        -- 配置成员在快照时的 id，仅审计
  object_type      VARCHAR(16) NOT NULL
  object_name      VARCHAR(128) NOT NULL
  target_version   VARCHAR(96) NOT NULL
  target_revision  VARCHAR(96) NULL
  sub_dir          VARCHAR(512) NOT NULL
  base_commit      VARCHAR(40) NULL
  UNIQUE (run_id, seq)
  UNIQUE (run_id, object_type, object_name)
```

全局唯一性（同一成员只属于一条配置）由服务层校验 + 成员表上的 `(workspace_id, object_type, object_name)` 唯一索引共同保证；`workspace_id` 冗余到成员表用于该索引。

### 3.2 旧表调整

- `evolution_targets`：删除 `object_type / object_name / sub_dir` 的 NOT NULL，保留一版写首个成员，供 V1 读端点与旧 run 兜底；下一版再删。
- `evolution_runs`：列不变；新增成员快照表后，旧列语义改为"首个成员"。
- `evolution_run_candidates`：新增 `object_type / object_name / object_revision`，记录命中成员。

### 3.3 迁移与回填（alembic 0035）

1. 建两张表与索引。
2. 回填成员：每条旧配置插入一条成员，取旧 `object_type / object_name / sub_dir`，定义快照从 `attribution_snapshot.definition` 迁移。
3. 回填 run 成员：每条旧 run 插入一行 `evolution_run_targets`。
4. 旧列改可空。双方言（SQLite / MySQL），回填用批量插入，单事务。

## 4. API 契约

### 4.1 目标配置

`GET /api/evolution/targets`：

```json
{
  "items": [{
    "id": "g-skills",
    "repoUrl": "https://github.com/acme/agent-skills.git",
    "defaultRef": "v2.4.0",
    "validationProjectId": "val-skills-2026q4",
    "testProjectId": "test-skills-2026q4",
    "primaryMetricKey": "resolved_rate",
    "attributionPackageId": "default-attribute-badcases",
    "attributionSkillName": "attribute-badcases",
    "enabled": true,
    "members": [
      {"objectType": "skill", "objectName": "deep-research", "subDir": "skills/deep-research", "definition": {"commit": "a3f9c21", "digest": "…"}},
      {"objectType": "skill", "objectName": "code-review", "subDir": "skills/code-review", "definition": {"commit": "a3f9c21", "digest": "…"}}
    ]
  }]
}
```

`POST /api/evolution/targets` / `PUT /api/evolution/targets/{id}` 请求体：

```json
{
  "repoUrl": "https://github.com/acme/agent-skills.git",
  "defaultRef": "v2.4.0",
  "validationProjectId": "val-skills-2026q4",
  "testProjectId": "test-skills-2026q4",
  "primaryMetricKey": "resolved_rate",
  "attributionPackageId": "default-attribute-badcases",
  "enabled": true,
  "members": [
    {"objectType": "skill", "objectName": "deep-research", "subDir": "skills/deep-research"},
    {"objectType": "skill", "objectName": "code-review", "subDir": "skills/code-review"}
  ]
}
```

错误码：`409 MEMBER_ALREADY_CONFIGURED`（成员已属于另一条配置）、`422 REPO_INVALID`（一次 `ls-remote` 校验仓库与 ref）、`422 TARGET_CONTENT_UNRESOLVED`（成员定义读不到）。

`GET /api/evolution/targets/{id}/versions` 不变：按配置仓库返回 tags。

### 4.2 向导目录与预览

`GET /api/evolution/catalogs` 的 `skill` / `agent` 合并为按配置返回：

```json
{"targets": [{"id": "g-skills", "name": "agent-skills", "repoUrl": "…", "defaultRef": "v2.4.0",
  "versions": ["v2.4.0", "v2.3.1"],
  "members": [{"objectType": "skill", "objectName": "deep-research", "subDir": "skills/deep-research"}]}]}
```

三个 preview 请求体新增 `targetId`；保留 `targetType / targetName / targetVersion` 作为兼容输入（映射到"含该对象的配置"）。

### 4.3 启动

`POST /api/evolution/launch`：

```json
{"targetId": "g-skills", "targetVersion": "v2.4.0", "from": "2026-10-12", "to": "2026-11-09",
 "policy": {"preset": "default"}, "cacheEnabled": true, "eval": {"mode": "ai-eval-platform"}}
```

后端逐成员解析 digest，冻结成员快照；`eval_config` 增加 `subDirs` 列表与共享的 `subDir`（首个成员，兼容）。

### 4.4 run 投影

`GET /api/evolution/runs/{id}` 新增 `targets[]`，旧 `target` 保留首个成员：

```json
{"target": {"type": "skill", "name": "deep-research", "version": "v2.4.0", "targetRevision": "digest:…"},
 "targets": [
   {"objectType": "skill", "objectName": "deep-research", "targetVersion": "v2.4.0", "targetRevision": "digest:…", "subDir": "skills/deep-research"},
   {"objectType": "skill", "objectName": "code-review", "targetVersion": "v2.4.0", "targetRevision": "digest:…", "subDir": "skills/code-review"}
 ]}
```

七步 `StepRangeCondition` 增 `targets[]`；第 2/3/5 步的行读 `candidate.object_name` 标注命中成员。

## 5. 后端流程

### 5.1 保存配置

1. `_normalize_write`：逐成员校验名称、子目录；成员去重；跨配置全局查重。
2. `_validate_remote`：一次 `git ls-remote` 校验仓库与 ref。
3. `TargetDefinitions.freeze`：逐成员读 `{sub_dir}/SKILL.md` 或 `AGENT.md`，写成员定义快照。
4. 同事务写 `evolution_targets` 1 行 + `evolution_target_members` N 行；置 `attribution_due=now` 触发绑定。

### 5.2 绑定归因

`BindingWorker` 按配置领 claim：快照存 `members[]`（各自 version / revision / definitionKey）→ `MatchCondition(成员列表)` → `list_object_events` 用 IN 查询，任一成员出现即关联 → `potential_cases` 用 `case.object_name ∈ 成员` → 每个 case 按自身对象查最新报告，缺的进同一批归因。失败整批记原因，重试沿用同一 `attribution_generation`，已完成 case 不重复。

### 5.3 启动与准备

`launch` 按 `targetId` 取配置 → 逐成员 `resolve` → `create_run` 同事务写 run + `run_targets` → prepare 逐成员 `freeze_revision`，`git cat-file -t {base}:{sub_dir}` 校验每个成员目录，任一缺失 `stage="subdirectory"`。

### 5.4 Patch 与评测

- `_allowed_paths(sub_dirs)` 返回多个 glob；`_edit_prompt` 列出成员；提交主题 `evolve(配置名@version)`。
- `EvalRequest.targets[]` → 平台 `asset_paths` 列全部成员 built path、`asset_types` 多 key；baseline 与 candidate 用同一冻结成员集合。
- `best_version` 取配置基线（成员共用），指标是整个 run 的一个分数。

## 6. 前端设计

### 6.1 配置弹窗

共享块（仓库、基线、归因 Skill、验证集/测试集 ID、主指标）+ 成员行（类型、名称、子目录）+ 「再加一个成员」。保存一次提交一条配置；错误定位到 `members[i].field`。启用/停用不在表单里切换（与本仓库 #628 的结论一致）：停用配置在总览的「已停用对象」分组里置灰展示，点「启用」恢复。

### 6.2 配置列表与总览

- 配置列表：一行一条配置，成员 chips 作明细；删除确认用配置名。
- 进化对象总览：按配置聚合潜在 bad case 与关联 Session，成员作为 chip 与明细；case 表新增"成员"列。

### 6.3 启动向导

单选配置（保留现有下拉交互）+ 只读成员面板 + 版本 + 共享测试工程摘要；请求体带 `targetId`。

### 6.4 run 详情

标题「配置名 N 个对象」；第 1 步展示成员与子目录、共享测试工程、改动范围；工作区折叠显示改动范围；第 2/3 步显示命中成员。

### 6.5 原型截图

截图只在本地保留，不随仓库分发（`.gitignore` 已忽略全部图片格式）。四个目标态页面：

- **配置弹窗**：共享块（仓库 / 基线 / 验证集与测试集工程 ID / 主指标 / 归因 Skill）+ 可增删的成员行。
- **向导第 1 步**：单选一条配置，成员只读列出，版本与测试工程共用。
- **run 详情**：配置名 + 成员 chip + 共享测试工程 + 改动范围。
- **工作区**：改动范围列出每个成员目录的 glob。

复现：本地打开原型（`?u=admin&page=overview&tab=targets`、`?demo=wizard1`、`?demo=run`），或运行 `plans/ui-prototype-v2/evidence/multi-object-target/capture.mjs before|after` 重新生成前后截图（before 态取 `git show HEAD` 的原始原型）。

## 7. 兼容与迁移

- 旧列保留一版、写首个成员；V1 读端点与历史 run 语义不变。
- 旧 run 无成员行时读路径回退旧列。
- 单成员配置的归因缓存键与改造前逐字相同。
- 同一成员不能属于多条配置；从 bad case 反查命中多条时返回 409。

## 8. 测试与门禁

- API：成员 CRUD、全局查重、级联删除、回填、旧 run 兜底、单成员缓存键逐字兼容、并集匹配、多目录 patch、多资产评测。
- 契约：OpenAPI 重生成与 `contract:check`。
- 前端：配置弹窗、列表、向导、run 详情、总览组件测试；E2E 加"一条配置两成员一次 run"。
- 门禁：`pnpm lint:api`、`typecheck:api`、`test:api`、`test`、`typecheck:web`、`contract:check`、`test:e2e`、`verify:flow`、`verify:docs`。

## 9. 风险与非目标

风险：身份迁移（成员表承担身份、旧列过渡）、成员重复归属、共享测试工程的硬约束、归因缓存键兼容、patch 范围放宽后的归属审计、绑定批次失败粒度。

非目标：不改评测平台资产契约；不支持跨仓成员；不允许同一成员属于多条配置；不改归因 Skill 执行器与提示词协议；不改 V1 六步游标映射；不在本设计内做"每成员独立评测工程"。

## 10. 原型与证据

- 原型：`plans/ui-prototype-v2/harness-evolution.html`（`?u=admin&page=overview&tab=targets`、`?demo=wizard1`、`?demo=run`）。
- 取证脚本：`plans/ui-prototype-v2/evidence/multi-object-target/capture.mjs`；内联脚本 `embed.py`。
- 截图只在本地保留（不进仓库）；评审以本地原型与重新生成的截图为准。
