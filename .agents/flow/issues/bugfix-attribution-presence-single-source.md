# 收敛归因关联为 presence 单一口径并清理文档/原型旧版本残留

[English](bugfix-attribution-presence-single-source.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-42
milestone: bugfix
depends: []
priority: P2
status: in-progress
scope:
  - .agents/flow/issues/bugfix-attribution-presence-single-source*
  - .agents/notes/implemented/architecture/2026-11-17-potential-matcher*
  - plans/ui-prototype-v2/harness-evolution.html
  - plans/fullstack-design/02-features.md
  - plans/fullstack-design/05-api-design.md
  - plans/fullstack-design/06-database-design.md
  - plans/fullstack-design/07-backend-implementation.md
  - plans/fullstack-design/08-frontend-implementation.md
  - plans/fullstack-design/README.md
  - plans/2026-11-23-pr421-plans-review.md
  - apps/api/tests/m10-02-potential-matcher/test_preview_api.py
adr:
  - ../../notes/implemented/architecture/2026-11-17-potential-matcher.md
github:
  number: 554
  url: https://github.com/Shadow-Azure/harness-evolution/issues/554
```

## 背景

PR #421 把 Session 关联从“目标版本精确匹配”改成“整棵 Session 树里出现所选类型和名称即关联”，并新增对象绑定 Skill、后台报告和按对象·版本复用。生产代码已经按 presence 运行，`test_unknown_and_nonmatching_revisions_are_associated` 也锁定了缺失版本与不同版本都可入选。

但同一批交付只改了一半：05/06/07/08 仍保留“identity 命中”“不做名称级猜测”“cache_key / rule-v1”等旧句；目标绑定字段、Skill 包表与 0023a–0031 迁移没有进入 05/06 契约；原型把第 4 步的“本次重算 Skill”写进了 `EV_STATE.wz.attributionSkill`，却没有带进 Run，Run 详情还在用旧的 `m.reused / m.fresh` 和旧缓存键文案。结果是同一份文档、同一个原型里同时存在 presence 与 version-exact 两套事实，评审者无法判断哪一条是现行行为。

## 目标

- 把 **对象类型 + 名称的出现** 定为唯一 Session 关联口径；`targetRevision` 只用于固定原文、报告和缓存范围，不再参与 Session 关联。`versionUnresolved` 明确为兼容字段、新批次恒为 0。
- 把对象绑定 Skill、空间 Skill 包、V2 报告字段和 0023a–0031 迁移补进 05/06 契约，消除“代码有、文档没有”的缺口。
- 清理 05/06/07/08/02/README 中与 presence 冲突的旧句，保留 legacy rule 的 `cache_key / rule-v1` 时明确标注为兼容路径。
- 修复原型数据流：第 4 步选中的 Skill 进入 Run 并可追溯；第 4 步与 Run 详情使用同一套复用/新增/缺报告计数；缓存开启且零报告时禁用启动；已有报告按来源 Skill 分组。
- 增加 API 级回归测试，验证缺失版本与不同版本的两个 Session 都进入 `preview/sessions`，且 `versionUnresolved=0`。

## 设计依据

- [05 §4.9 / §4.11 / §4.20](../../../plans/fullstack-design/05-api-design.md)：向导预览、target CRUD、归因预览契约。
- [06 §4.2.2 / §5.1 / §5.8 / §7.5 / §9](../../../plans/fullstack-design/06-database-design.md)：报告字段、target 列、写入语义、关联口径、迁移。
- [07 §5.12–5.14](../../../plans/fullstack-design/07-backend-implementation.md)：PotentialMatcher、归因生成与预览端点。
- [08 §9.2 / §9.5 / §10](../../../plans/fullstack-design/08-frontend-implementation.md)：向导、对象配置、运行详情。
- [02 对象绑定归因](../../../plans/fullstack-design/02-features.md#对象绑定归因)：功能叙事与验收摘要。
- [潜在匹配决策](../../notes/implemented/architecture/2026-11-17-potential-matcher.md)：presence 口味的单一实现与理由。

## 实现内容

- **05**：`stats` 与 `preview/attribution` 返回补 `bySkill/missing`；§4.11 target body 增加可空 `attributionPackageId`，补空间 Skill 包列表/上传/详情/下载/删除接口；§4.20 把“关联与缓存键使用 targetRevision”拆成“关联按 presence、缓存按 targetRevision”；4.9 的“匹配接受 body hash”改为“Session 关联按类型和名称”。
- **06**：`evolution_targets` 补 `attribution_package_id / attribution_generation / attribution_snapshot`；新增 `attribution_skill_packages` 与 `attribution_skill_package_bindings` 表；`probe_reports` 补 `report_schema_version / report_payload / execution_manifest / execution_manifest_hash / attribution_skill_name / analyzed_at / binding_generation`；§7.5 的“对象进入点”“Session 关联口径”“预览缓存口径”统一为 presence，legacy `cache_key` 单列；§9 补 0023a–0031 迁移摘要。
- **07**：§5.12 的“触发点身份”只描述 target 内容解析，不再要求 identity 参与 Session 关联；§5.13 区分“绑定包最新报告”与 legacy rule 的 cache_key；§5.14 的 `preview/sessions` 改 presence、`preview/attribution` 改最新报告 + `bySkill/missing`；补 Skill 包解析与绑定批次的职责边界。
- **08**：Step 2 删除“按 body hash 匹配”；Step 4 已写的新统计与零命中禁用保留；§10.1 的“统计四数”改为“潜在 / 可归因 / 非该对象 / 复用 / 缺报告 / 本次新增”；Run 详情补“本次 Skill”；§9.5 表单补归因 Skill，新增空间 Skill 资源库的读/传/删说明；历史内联提示词只读保留，不新增选择器。
- **02 / README**：F26 ④ 改成新统计；README D23 补回日期、理由与 05/06/07 链接，不覆盖决策可追溯性。
- **原型**：`evMakeRun` / `evWzRun` / `ev-wz-start` 传递 `attributionSkill`；`evRunModel` 统一 `hasReport / reused / fresh / missing`；Run 详情与第 4 步共用计数并按来源 Skill 分组；缓存开启且零报告时禁用启动；target 编辑保留历史内联绑定的只读语义。
- **测试**：`test_preview_api.py` 增加“不同版本 + 缺失版本”同时关联的 API 用例，断言 `summary.associated=2`、`versionUnresolved=0`。
- **Note**：更新 `2026-11-17-potential-matcher`，补“文档/原型不得重新引入 version-exact 关联”的后果。

## 实施步骤

1. 新增 issue 并同步 GitHub 编号，状态转 in-progress。
2. 按 05 → 06 → 07 → 08 → 02/README 顺序改文档，先收敛口径，再补契约字段。
3. 改原型数据流、计数与 Skill 分组，跑 headless Chrome 手工验收。
4. 补 `test_preview_api.py` 回归用例并更新 owning Note（含英文侧与配对记录）。
5. 跑文档、流程、门禁与聚焦 API 测试；提交、开 PR、按 CI 结果合入。

## 依赖与交付边界

- 依赖：无。
- 只改文档、原型、流程文件、测试与 Agent Note；不改生产匹配算法、数据库结构、OpenAPI 生成物或前端生产组件。
- 生产行为已按 presence 运行；本 issue 不恢复版本精确匹配，也不把历史内联提示词改成可重新选择。

## 独立验证

```sh
pnpm test:api -- tests/m10-02-potential-matcher/test_preview_api.py tests/m10-02-potential-matcher/test_matcher.py
pnpm lint:docs
pnpm verify:docs
pnpm verify:flow
pnpm test:gates
```

- 聚焦 API 测试通过；新增用例返回两个关联 Session，`versionUnresolved=0`。
- 四个文档/流程门禁全绿。
- 原型实测：关闭缓存选 `harness-trace-review` 启动，Run 对象带 `attributionSkill=harness-trace-review`；Run 详情与第 4 步对同一 Run 显示相同的复用/新增/缺报告数；缓存开启且候选全无报告时启动按钮 `disabled`。

## 验收标准

- 05/06/07/08 中不存在“Session 关联按 targetRevision / identity 命中”的现行口径；`versionUnresolved` 只作为历史兼容字段出现。
- 05 §4.11 有 `attributionPackageId` 与空间 Skill 包接口；06 §5.1 有三个绑定列和两张包表；§9 有 0023a–0031 迁移摘要。
- 02 F26、08 §10.1 与 Run 详情不再写“四数”；README D23 保留日期与 05/06/07 链接。
- 原型选中 Skill 后 Run 可追溯；第 4 步与 Run 详情计数一致；缓存零命中禁用启动；已有报告按来源 Skill 分组。
- API 回归用例通过；全仓门禁通过；PR 合入后 `main` 上不再出现本 issue 列出的旧句。

## 门禁与 CI

- `pnpm test:api -- tests/m10-02-potential-matcher/test_preview_api.py tests/m10-02-potential-matcher/test_matcher.py`
- `pnpm lint:docs`、`pnpm verify:docs`、`pnpm verify:flow`、`pnpm test:gates`
- 提交与 PR 标题带 `(#N)`；PR 描述列出文档/原型验收证据。

## 非目标

- 不改变 `PotentialMatcher.associated_sessions` 的 presence 算法，不恢复版本精确匹配。
- 不改数据库结构、迁移文件、OpenAPI 生成物或生产 Vue 组件。
- 不新增 Skill 包上传协议、不接入内网 Agent、不改聚类/评测。
- 不为历史内联提示词新增可编辑选择器；只保留读取与历史回放。
