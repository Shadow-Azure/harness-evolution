# 按 label 将公共 badcase 划分到空间

[English](bugfix-evolution-label-allowlist.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-60
milestone: bugfix
depends: []
priority: P2
status: done
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - plans/**
  - .agents/**
  - docs/**
adr: []
github:
  number: 582
  url: https://github.com/Shadow-Azure/harness-evolution/issues/582
```

## 背景

生产环境中的 badcase 统一上报到公共仓库，平台定期从同一个仓库拉取多种类型的数据，`items[].meta_data.label` 表示 badcase 大类型。空间需要配置自己接收的 label；同一个 label 可以同时配置给多个空间，匹配的数据应同时对这些空间可见并参与各自后续自进化。

## 目标

在空间管理增加「Badcase 类型」页签维护当前空间接受的 label。公共仓库同步后，平台按 label 建立 badcase 与空间的多对多分配关系，使列表、Session、统计和自进化统一使用同一空间数据边界。

## 设计依据

遵循 [自进化域](../../../plans/fullstack-design/02-features.md#22-自进化域) 与公共 badcase 同步设计。本 issue 补充公共目录到空间数据面的划分规则，实施时同步对应设计章节与 Agent Note。

## 问题描述、分析过程与根因

1. `apps/api/app/third_party_api/bad_case_query/http.py` 调用 GET `{HE_BAD_CASE_QUERY_BASE_URL}/bad-cases`，参数是 bad_case_id、offset、limit，没有 label 筛选参数。
2. 同目录 `models.py` 中 `BadCaseItem.meta_data` 是 `Any | None`，没有显式 label 契约。代码可承载 label，但尚未核实真实响应中的存在性与类型。
3. `apps/api/app/service/acquisition/bad_case_catalog_sync.py` 的 `_row` 保留完整 meta_data，但目录同步按递增 ID 将公共记录直接 upsert 到 `bad_cases`，没有解析 label 或执行空间分配。
4. `bad_cases.bad_case_id` 是全局主键且每行只有一个 `workspace_id`。该模型无法表达“同一公共 badcase 因同一 label 同时属于多个空间”；把记录复制到多行也会与全局主键冲突。
5. 当前列表、Session、统计和 `PotentialMatcher.associated_sessions` 都通过 `bad_cases.workspace_id` 限定空间。若只在自进化入口过滤，其他空间数据面会与自进化口径不一致，也无法让同一 badcase进入多个空间。
6. `apps/web/src/pages/workspaces/Admin.vue` 缺少 label 分配规则入口，后端也没有规则存储、重算和未分配观测能力。

结论：根因是公共 badcase 事实与空间归属耦合在 `bad_cases.workspace_id` 单值字段中，同时缺少 label 到空间的多对多规则及同步后的统一分配过程。真实 label 类型与完整性仍需脱敏样本确认；上述结论来自静态代码分析，未查询生产数据。

## 实现内容

唯一推荐方案：把 `bad_cases` 作为公共仓库事实表，新增空间 label 规则表和 badcase—空间关联表，由目录同步与规则重算共同维护关联；所有空间数据查询统一通过关联表限定范围。

- 新增 `workspace_bad_case_labels(workspace_id, label)`，联合唯一；同一 label 可对应多个 workspace。空间管理新增「Badcase 类型」页签，V1 手动添加、删除和保存。全局管理员与空间管理员可写，后端强制权限检查。
- 新增 `workspace_bad_cases(workspace_id, bad_case_id, assignment_source, label, assigned_at)`，以 `(workspace_id, bad_case_id, assignment_source)` 唯一；`assignment_source` 三态 `legacy_owner` / `direct_ingest` / `catalog_label`，`label` 只落在 `catalog_label` 行。`bad_cases` 保存一份公共原始事实，不再以单值 `workspace_id` 表达归属；迁移把现有记录的 workspace_id 回填为 `legacy_owner` 关联，再逐步移除旧字段依赖。SQLite/MySQL 同步迁移。
- 公共同步验证 `meta_data.label` 后先幂等 upsert 公共事实，再查询接受该 label 的全部空间，为每个空间幂等写入关联。同一 badcase 可因此属于多个空间，但原始记录只保存一次。
- 保存 label 配置后，在同一受控任务中按本地公共事实重算受影响 label 的关联：新增规则补齐历史数据，删除规则移除该空间的实时关联；不需要回退同步游标或重新请求上游。已创建运行持久化的候选和报告不被删除。
- 列表、Session、统计、额度计数、归因候选和自进化取数全部由 `workspace_bad_cases` 关联限定；因此自进化无需再实现一套独立 label 过滤，原有对象、版本、时间和证据条件继续取交集。
- 建议 V1 label 为非空字符串，区分大小写精确匹配；配置去重并拒绝空白和首尾空格。缺失、null、空串和非字符串 label 的公共记录保留但不分配，纳入同步状态中的 invalid/unassigned 计数，不进入默认空间。
- 上游更新历史 badcase 的 label 时，先删除旧 label 产生的关联，再按新 label 重建；整个重分配具备事务或可恢复任务边界，避免数据同时消失或重复。

## 实施步骤

1. 核实脱敏 label 样本，固定 label 契约、迁移方案和 Agent Note。
2. 实现两张关系表、现有 workspace_id 数据迁移、规则 API 与共享协议。
3. 改造公共目录同步和配置重算任务，补未分配/非法 label 观测。
4. 将所有空间读路径切到关联表，完成管理页签与跨栈验证。

## 依赖与交付边界

不依赖上游新增筛选接口，公共仓库仍只配置一个来源且同步游标保持全局。真实 label 类型确认是实施前置条件。本 issue 负责空间划分及其所有读路径；不修改上游仓库的数据生产方式。

## 独立验证

合成公共数据含 A/B、无 label、null、数字 label；空间一接受 A，空间二接受 A/B。执行 `pnpm test:api:serial`、`pnpm test:db`、`pnpm test:db:mysql`、`pnpm test`、`pnpm test:e2e`。验证 A 记录只存一份但关联两个空间，B 只关联空间二，非法/未配置 label 保留且不分配；新增规则能补齐历史关联，删除规则只移除目标空间关联；列表、统计、Session 和 full/cluster_only 自进化看到一致集合，重试不会产生重复关联，既有运行可继续恢复。

## 验收标准

- 同一 label 可配置给多个空间，同一 badcase 原始事实只存一份并正确关联所有匹配空间。
- 配置持久化且权限隔离；新增、删除规则会确定性重算历史关联，非管理员写入被拒绝。
- 缺失、非法和未配置 label 不进入任何空间，并有可观测计数。
- 列表、Session、统计、额度和自进化使用相同空间集合；同步及重算重试保持幂等，既有运行不被配置变化破坏。

## 门禁与 CI

实现运行 `pnpm contract:generate`、`pnpm contract:check`、`pnpm typecheck`、`pnpm typecheck:web`、`pnpm lint:api`、`pnpm lint:web`、`pnpm test:db`、`pnpm test:db:mysql` 及上述行为测试，CI 纳入新增用例且覆盖率不少于 80%。文档运行 `pnpm record:i18n -- .agents/flow/issues/bugfix-evolution-label-allowlist.md`、`pnpm verify:flow`、`pnpm lint:docs`。本次创建 issue 不代表这些产品验收已通过。

## 非目标

不改上游接口、不删除公共原始 badcase、不推断或补全 label、不做标签字典、不追溯修改已经创建的运行输入。

