# 同仓多 Skill / Agent 作为一条进化对象

[English](m28-01-multi-member-evolution-target.en.md) | 中文

```yaml flow
kind: issue
id: m28-01
milestone: m28
depends:
  - m5-02
  - m10-02
  - m12-03
priority: P1
status: ready
scope:
  - apps/api/app/db/**
  - apps/api/app/service/**
  - apps/api/app/api/**
  - apps/api/app/third_party_api/**
  - apps/api/tests/**
  - apps/web/src/**
  - packages/contracts/**
  - tests/e2e/**
  - plans/**
  - scripts/doc-budgets.manifest.json
  - .agents/**
adr: []
github:
  number: 640
  url: https://github.com/Shadow-Azure/harness-evolution/issues/640
```

## 背景

### 问题场景

同一个代码仓里常同时存在多个 skill 和 agent，例如 `skills/deep-research` 与 `skills/code-review`：它们共享仓库、基线与评测工程，bad case 也常来自同一批 Session。今天 `evolution_targets` 一行只承载一个对象——唯一约束是 `(workspace_id, object_type, object_name)`，作用域 `sub_dir`、验证集/测试集测试工程与绑定归因都挂在这一行上。要把这一组对象作为一条进化对象配置，只能建 N 条配置，于是：

- 仓库、基线、测试工程 ID、主指标、归因 Skill 重复填 N 次；
- bad case 归属分散在 N 条配置，无法作为一个进化对象统一筛选、统一归因；
- 一次 run 只能针对一个对象，用不上"这些 case 往往同时涉及多个对象"的事实；
- patch 只允许改一个目录，评测只提交一个资产。

### 诉求

- **配置一次**：仓库地址、基线分支或标签、验证集/测试集测试工程 ID、主指标 key、归因 Skill、启用状态，一条进化对象只填一次。
- **成员逐个列**：每个成员有类型（skill / agent）、名称、子目录；成员共享上面的配置，但各自冻结定义、各自关联 bad case。
- **一次 run 一起进化**：共享同一个基线 commit；patch 允许范围覆盖全部成员目录；评测一次提交全部成员资产；提交信息与七步展示能说清成员。
- **总览按配置看**：一条配置一行，看整体潜在 bad case 与关联 Session；成员作为 chip 与明细，case 表标出命中成员。
- **兼容不破**：历史配置回填为单成员配置；历史 run 无成员快照时按旧列读取；V1 读端点在兼容窗口内语义不变。

### 讨论与结论

2026-11-26 的讨论先按"每个成员一条配置 + 向导多选"做了一版原型，评审后确认不符合预期：配置重复、bad case 归属分散、向导被迫引入"主对象"。随后按下列三种形态重新对比：

| 形态 | 描述 | 结论 |
|---|---|---|
| A | 一条配置 = 一个进化对象，含同仓多个成员 | **采用** |
| B | 每个成员一条配置，向导多选同仓对象 | 否决：配置重复、归属分散、"主对象"概念 |
| C | 只做批量填表，run 仍单对象 | 否决：解决不了"一起进化" |

据此确定三条边界：

- **共享**：仓库、基线、验证集/测试集测试工程、主指标、归因 Skill、启用。
- **成员**：类型、名称、子目录、定义快照（commit / digest / 原文）。
- **两条硬约束**：成员必须同仓（一个 run 一个 `base_commit`）；同一成员只能属于一条配置（否则 bad case 与归因报告歧义）。向导因此恢复单选，不再有"主对象"。

外部契约已核对：评测平台 `ai-eval-platform@main d5231fe` 的 `asset_override.asset_paths` 是 `list[str]`、无数量上限、整字段替换、一次 launch 共用一个 commit、任一路径缺失整单 422；因此测试工程与主指标由成员共享，与平台"一次 launch 一个模板"一致。

### 原型方案截图

截图只在本地保留，不随仓库分发（`.gitignore` 已忽略全部图片格式）。目标态的四个页面：

- **配置**：共享块（仓库 / 基线 / 验证集与测试集工程 ID / 主指标 / 归因 Skill）+ 可增删的成员行。
- **启动向导**：单选一条配置，成员只读列出，版本与测试工程共用。
- **run 详情**：配置名 + 成员 chip + 共享测试工程 + 改动范围。
- **工作区**：改动范围列出每个成员目录的 glob。

复现：本地打开 `plans/ui-prototype-v2/harness-evolution.html`（`?u=admin&page=overview&tab=targets`、`?demo=wizard1`、`?demo=run`），或运行 `capture.mjs before|after` 重新生成前后截图；修改前对照与说明见 [18 §6.5](../../../plans/fullstack-design/18-multi-member-evolution-target.md#65-原型截图)。

## 目标

- 一条配置可保存同一仓库的多个 skill / agent，且只产生一条 `evolution_targets` 与 N 条 `evolution_target_members`。
- 保存时校验成员名称、子目录、测试工程 ID、主指标；重复成员与跨配置重复成员被拒绝。
- 绑定归因按配置一批执行：任一成员出现的 Session 都关联，case 按自身对象归因；单成员配置的缓存键与改造前逐字相同。
- 一次 run 快照成员列表；patch 允许范围与评测资产覆盖全部成员目录；任一成员目录缺失时 prepare 即失败。
- 前端配置、列表、向导、run 详情、总览按"配置 + 成员"两级呈现，交互回到单选配置。
- 历史配置回填为单成员配置，历史 run 与 V1 读端点保持兼容。

## 设计依据

- [18 §1 背景与决策](../../../plans/fullstack-design/18-multi-member-evolution-target.md#1-背景与决策)：诉求、三种形态对比、共享与成员边界。
- [18 §2 领域模型](../../../plans/fullstack-design/18-multi-member-evolution-target.md#2-领域模型) 与 [18 §3 数据模型](../../../plans/fullstack-design/18-multi-member-evolution-target.md#3-数据模型)：两张新表、索引、迁移回填、旧列兼容。
- [18 §4 API 契约](../../../plans/fullstack-design/18-multi-member-evolution-target.md#4-api-契约)：target CRUD、catalog、launch、run 投影的请求与响应。
- [18 §5 后端流程](../../../plans/fullstack-design/18-multi-member-evolution-target.md#5-后端流程)：保存、绑定、启动、prepare、patch、评测与终态。
- [18 §6 前端设计](../../../plans/fullstack-design/18-multi-member-evolution-target.md#6-前端设计)：四个页面与组件、请求映射、原型截图。
- [06 数据库表结构设计](../../../plans/fullstack-design/06-database-design.md)：双方言、迁移与命名惯例。
- [05 后端接口设计](../../../plans/fullstack-design/05-api-design.md) 与 [07 后端实现设计](../../../plans/fullstack-design/07-backend-implementation.md)：路由、服务与仓储分层。
- [08 前端实现设计](../../../plans/fullstack-design/08-frontend-implementation.md)：页面组件与数据流。

## 实现内容

- `apps/api/app/db/models/domain.py`、`db/models/evolution.py`：新增 `evolution_target_members`、`evolution_run_targets`；`evolution_run_candidates` 增 `object_type / object_name / object_revision`；`evolution_targets` 旧列改可空。
- `apps/api/alembic/versions/0035_*.py`：建表与索引、回填成员与 run 成员、双方言。
- `apps/api/app/db/crud/evolution_targets.py`：记录带 `members`，insert / update 同事务写成员，`find` 改 join 成员表，删除级联。
- `apps/api/app/service/evolution/targets.py`：写模型带 `members`，成员校验与全局查重，`ls-remote` 一次，逐成员冻结定义；`enabled_config_by_id` 与 `enabled_config_for_object` 双入口。
- `apps/api/app/service/evolution/binding_worker.py`、`attribution.py`、`attribution_context.py`：按配置一批、成员快照、上下文 `targets[]`、缓存键单成员逐字兼容。
- `apps/api/app/service/evolution/potential.py`、`launch.py`、`prepare.py`：`MatchCondition(targets[])`、按配置启动、成员快照与并集匹配。
- `apps/api/app/service/evolution/patch_source.py`、`git_candidate.py`、`third_party_api/git/workspace.py`：多目录 `allowed_paths`、成员提示词、提交主题、逐成员 `cat-file` 预检。
- `apps/api/app/service/evolution/engine/contracts.py`、`eval_poller.py`、`third_party_api/eval_gateway/ai_eval_platform.py`：`EvalRequest.targets[]`、多资产一次提交。
- `apps/api/app/service/evolution/runs.py`、`stages.py`、`apply_final.py`、`service/overview/targets.py`、`service/catalogs.py`：配置 + 成员两级投影与聚合。
- `packages/contracts`：OpenAPI 重生成与类型。
- `apps/web`：配置弹窗共享块 + 成员行、配置列表、向导单选配置 + 只读成员面板、run 详情、总览与 case 表成员列。
- `plans/ui-prototype-v2`：原型与取证脚本、截图。
- `plans/fullstack-design/18-multi-member-evolution-target.md`：设计章节。

## 实施步骤

1. 数据层：建两张表、candidates 三列与回填；仓储支持配置 + 成员。
2. 配置服务：写模型带成员、校验与全局查重、一次 `ls-remote`、逐成员冻结。
3. 绑定归因：按配置一批、成员快照、上下文与缓存键兼容。
4. 启动与准备：`MatchCondition(targets[])`、`targetId` 启动、run 成员快照、逐成员 `cat-file`。
5. Patch 与评测：多目录 `allowed_paths`、提交主题、`EvalRequest.targets[]` 与平台多资产。
6. 投影与前端：run 详情、七步、总览、配置页、向导；契约重生成。
7. 测试与文档：单元、契约、E2E、fixture、Agent Note、architecture 与 compatibility 同步。

## 依赖与交付边界

- 依赖：`m5-02`（目标配置 API）、`m10-02`（潜在匹配）、`m12-03`（真实 patch / 评测）。
- 交付边界：只做"同仓多成员"的配置、绑定、启动、patch、评测与展示；不改评测平台契约、不支持跨仓成员、不允许同一成员属于多条配置。
- 兼容：旧列保留一版写首个成员；历史 run 无成员行按旧列兜底；V1 读端点语义不变；旧列收紧或删除留到下一版。

## 独立验证

```sh
pnpm test:api
pnpm test:web
pnpm typecheck
pnpm typecheck:web
pnpm contract:check
pnpm test:e2e --pattern m5-target-config
pnpm test:e2e --pattern m10-06
pnpm verify:flow
pnpm verify:docs
```

- 预期：成员 CRUD、全局查重、级联删除、回填与旧 run 兜底用例通过；单成员缓存键与改造前逐字相同；一条配置两成员一次 run 的 E2E 用例通过；契约与文档门禁全绿。

## 验收标准

- 一条配置可保存同一仓库的两个成员；重复成员与跨配置重复成员被拒绝，错误定位到成员字段。
- 向导只选配置；run 详情展示成员、子目录、共享测试工程与改动范围；第 2/3 步显示命中成员。
- 绑定归因按配置一批；任一成员出现即关联；case 按自身对象归因；单成员缓存键逐字兼容。
- 一次评测提交全部成员资产；任一成员目录缺失时 prepare 以 `stage="subdirectory"` 失败。
- 历史配置回填为单成员配置；历史 run 与 V1 读端点行为不变。
- 原型截图、设计章节与 Agent Note 同 PR 落地，流程与文档门禁通过。

## 门禁与 CI

- `pnpm lint:api`、`pnpm typecheck:api`、`pnpm test:api`、`pnpm test`、`pnpm typecheck:web`、`pnpm contract:check`、`pnpm test:e2e`、`pnpm verify:flow`、`pnpm verify:docs`。
- 提交与 PR 标题带 GitHub 编号；实现 PR 的 diff 必须落在本 issue 的 scope 内。

## 非目标

- 不改评测平台的资产契约与错误码。
- 不支持跨仓库成员，也不把 run 模型升级成多仓多 commit。
- 不允许同一成员同时属于多条配置。
- 不改归因 Skill 的执行器、提示词协议与缓存策略版本。
- 不改 V1 六步游标的只读映射与 V1 端点语义。
- 不做"每成员独立测试工程"或"每成员独立评测"。
