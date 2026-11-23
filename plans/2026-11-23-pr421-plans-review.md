# PR #421 检视：plans 文档与原型中的对象绑定归因

- 检视对象：[PR #421](https://github.com/Shadow-Azure/harness-evolution/pull/421)（已合入 `main`）
- 合并提交：`d33b2c45`；第一父提交 / merge base：`6d473733`
- 检视基线：`main` @ `2f4bce1d`（本检视文档写于此 worktree）
- PR 实现 issue：[#417](https://github.com/Shadow-Azure/harness-evolution/issues/417)
- owning Note：[2026-11-17-potential-matcher.md](../.agents/notes/implemented/architecture/2026-11-17-potential-matcher.md)
- 日期：2026-11-23

> 范围只覆盖用户指定的两个位置：`plans/ui-prototype-v2/harness-evolution.html` 与 `plans/fullstack-design/`。PR #421 整体有 324 个文件；本检视不评价其余 317 个文件。

## §0 结论

**有回退，但不是“git 层面的文件回退”。**

1. **机械回退：没有。** `git merge-base d33b2c45^1 d33b2c45^2` 正好等于 `d33b2c45^1`，即 PR 合入时第一父提交就是 merge base；`6d473733..d33b2c45` 只改了这两个目录内的 7 个目标文件。之后 `main` 上的 #535 改动也仍在。不存在“把 main 上更新的文件整段覆盖掉”的情况。
2. **语义回退：有，且是有意的。** `d952464c fix: admit attribution cases by object presence across the session tree (#417)` 把 Session 关联从“目标版本 / revision 精确匹配”改回“整棵 Session 树里出现所选类型和名称即关联”。这等于撤掉 #294 建立的版本精确口径。PR 描述与 Agent Note 都给了理由：生产轨迹可能缺版本，或记录的是与本次分析原文不同的历史版本；只认快照版本会让有明确调用证据的 Badcase 无法分析。
3. **真正的问题：回退只改了一半。** 同一批文档里仍保留旧的“版本精确匹配”“不做名称级猜测”“cache_key / rule-v1 预览”表述；原型只改了向导第 4 步、对象/Skill 绑定与资源库，Run 详情与启动数据流仍是旧口径。于是同一份文档、同一个原型里同时存在两套事实。

一句话：**方向可以理解，但 PR 没有把“旧口径”清理干净；这不是回退本身的问题，而是回退后的单一事实源没有建立。**

> 后续：本检视的 D1–D6 已由 [#554](https://github.com/Shadow-Azure/harness-evolution/issues/554) 处理，修复内容是把 presence 定为唯一关联口径、补齐绑定字段/Skill 包/迁移契约，并修正原型数据流与 Run 详情计数。

## §1 变更树与一页速览

### 1.1 目标目录内的实际改动（`6d473733..d33b2c45`）

| 文件 | 增/删 | 作用 |
|---|---:|---|
| `plans/fullstack-design/02-features.md` | +15/-1 | 更新 F26 的 Session 关联口径；文末新增“对象绑定归因”一节 |
| `plans/fullstack-design/05-api-design.md` | +3/-3 | 更新 `stats` 字段与 Session 摘要口径；更新归因预览返回字段 |
| `plans/fullstack-design/06-database-design.md` | +6/-6 | 删除部分 cache_key 叙述；新增“对象出现”行 |
| `plans/fullstack-design/07-backend-implementation.md` | +7/-4 | 新增 `run_skill` 协议；新增“关联口径” |
| `plans/fullstack-design/08-frontend-implementation.md` | +6/-6 | Step 2 / Step 4 文案；Run 详情“运行中”文案 |
| `plans/fullstack-design/README.md` | +1/-1 | 重写 D23 决策行 |
| `plans/ui-prototype-v2/harness-evolution.html` | +36/-29 | 向导第 4 步、对象 Skill 绑定、Skill 资源库 |

### 1.2 一页速览

PR 421 的产品主张是：**进化对象绑定一个归因 Skill；保存绑定后后台逐 Badcase 产报告；向导第 4 步按对象·版本复用最新报告，或为本次 Run 单次换 Skill 重算。** 目标目录的改动应回答三件事：

- 旧“版本精确匹配”是否被新“类型 + 名称出现”完整替换；
- 新的 Skill 包、对象绑定字段是否进入 API / DB / 前端契约；
- 原型是否演示了“本次 Run 只对本次生效”的换 Skill 路径。

三条都没有闭环：第一条只替换了部分句子，第二条基本没有进入契约，第三条只改了选择器、没有进入 Run 数据。

### 1.3 回退判定表

| 判定 | 结论 | 证据 |
|---|---|---|
| 是否覆盖了 `main` 上更新的目标文件 | 否 | merge base = 第一父提交；`git diff 6d473733 d33b2c45 --stat` 仅上述 7 文件 |
| 是否把版本精确关联改回名称/类型关联 | 是，有意 | `d952464c`；`potential.py` 删除 `_event_matches`，`version_unresolved` 恒 0 |
| 是否清理了旧口径的所有文案 | 否 | 05/06/07/08 仍同时存在 identity 与 presence 两套规则 |
| 是否记录了完整的新 API / DB 契约 | 否 | 05 §4.11 无 `attributionPackageId`；06 §5.1 无绑定列、无新表、无 0023a–0031 迁移 |
| 原型是否演示了“本次 Run 换 Skill” | 否 | 选择器值写入 `EV_STATE.wz.attributionSkill`，但 `evMakeRun` 不接收、Run 对象不保存 |

## §2 主要发现

> 以下每条按 `docs/review.md` 的五段格式写。结论留给维护者。

### D1（P1，fact）版本精确 / 类型名称出现两套规则同时存在

**位置**

- [05-api-design.md](fullstack-design/05-api-design.md#L951)：“匹配接受 body hash、原始版本与 M9 legacy `object_revision`”。
- [05-api-design.md](fullstack-design/05-api-design.md#L1282)：“关联与缓存键使用后者”（后者指 `targetRevision`）。
- [06-database-design.md](fullstack-design/06-database-design.md#L905)：“对象进入点 … 事件 identity 命中目标 revision 候选集”。
- [06-database-design.md](fullstack-design/06-database-design.md#L906)：“Session 关联口径 … `versionUnresolved` … `skipped` 是没有任何 identity 匹配的根”。
- [07-backend-implementation.md](fullstack-design/07-backend-implementation.md#L1278)：“对象进入点 … identity 命中候选集”。
- [07-backend-implementation.md](fullstack-design/07-backend-implementation.md#L1314)：“只列 identity 匹配的 Session”。
- [08-frontend-implementation.md](fullstack-design/08-frontend-implementation.md#L677)：“‘出现’都按归一化 body hash 匹配”。

**现象**

同一批文档里，紧邻的新增句已经改成“整棵 Session 树中存在所选类型与名称即关联”，但上述旧句仍在。06 §7.5 甚至在同一张表里同时列出“对象进入点（identity 命中）”和“对象出现（类型+名称）”，二者对同一 Session 会给出不同结论。

**问题**

实现侧已经是 presence-based：`PotentialMatcher.associated_sessions()` 只按 `object_type + object_name` 取事件，`version_unresolved=0`。文档读者按 05/06/07 的旧句实现，会把缺版本或不同版本的历史轨迹重新排除，正好复现 PR 要修的 Badcase 不可分析问题；按新句实现，又会与同页的“skipped 定义”冲突。

**预判**

这是本次 PR 最值得修的部分，不是补充说明，而是把旧 identity 段落改写成 presence 口径：

- 05 §4.9 的“匹配接受 body hash…”改成“Session 关联按类型 + 名称；body hash 只用于选定原文、报告和缓存”。
- 05 §4.20 的“关联与缓存键使用后者”拆成两句：关联不使用 `targetRevision`，缓存仍以选定快照为范围。
- 06 §7.5 删除“对象进入点”的 identity 条件，或明确它只用于“选定原文”而非“Session 关联”；`Session 关联口径` 行的 `versionUnresolved` 定义改成“兼容字段，新批次恒 0”。
- 07 §5.12 的“触发点身份”“preview/sessions 只列 identity”同步改写。
- 08 Step 2 的“body hash 匹配”删除。

**结论**

待维护者确认。建议按 owning Note 的“按类型和名称关联，保留观测版本”作为唯一口径。

---

### D2（P1，fact）对象绑定与 Skill 包没有进入 API / DB 契约

**位置**

- [05-api-design.md](fullstack-design/05-api-design.md#L1042-L1067)：target CRUD 的说明、示例与 body 仍只有 `objectType/objectName/repoUrl/subDir/defaultRef/validationProjectId/testProjectId/enabled`。
- [06-database-design.md](fullstack-design/06-database-design.md#L548-L568)：`evolution_targets` 表仍只有旧列，没有 `attribution_package_id / attribution_generation / attribution_snapshot`。
- [06-database-design.md](fullstack-design/06-database-design.md#L960-L990)：迁移清单只写到 `0020/0021`，没有 PR 新增的 `0023a / 0024a / 0025a / 0026a / 0027 / 0028 / 0028a / 0029 / 0030 / 0031`。
- 实际 schema：`apps/api/app/db/models/domain.py:478-484` 有上述三列；`attribution_skill_packages` 表在 `domain.py:616`。

**现象**

PR 新增了空间 Skill 包上传/详情/下载/删除、对象绑定、绑定批次、后台报告等接口和表；05/06 只在归因预览和 §7.5 提了一句“绑定包”“绑定批次”，没有 contract 级描述。全仓搜索 `attributionPackageId` 在 `plans/fullstack-design` 只命中 05:1288 一句“启动请求可带”，没有字段定义、类型、约束或错误码。

**问题**

- 前端拿不到 target 字段名与可空性，容易把 `attributionPackageId` 当成必填或漏掉“不传则用默认包”。
- 迁移文档不完整，部署/回滚时无法从 06 查到新表与新列；`06` 的“迁移顺序与守卫”仍以 0020/0021 为结尾。
- 新增的 `attribution_skill_packages` / `attribution_skill_package_bindings` / `probe_reports.attribution_skill_name` / `binding_generation` 等没有表级定义，和 06 开头“一个事实一个 home”的约定冲突。

**预判**

至少补三块：

1. 05 §4.11 target CRUD body 增加 `attributionPackageId`（可选，缺省为空间默认包），并写 409“包已绑定/不存在”等错误。
2. 05 新增 Skill 包 API 小节：列表、上传、详情、下载、删除、绑定目标查询；与 02 新增节呼应。
3. 06 §5.1 增加三列；新增 Skill 包表与绑定表；§9 迁移清单补 0023a–0031，并说明与 0020/0021 的先后关系。

**结论**

待维护者确认。若本轮只做“设计稿跟随实现”，这是必须补的；若刻意把包 API 留给下一份设计，应在 02/05 明确“不在本轮契约范围”。

---

### D3（P2，fact）缓存口径仍是两套：cache_key / rule-v1 与“最新完成报告”

**位置**

- [05-api-design.md](fullstack-design/05-api-design.md#L948)：归因段 summary 仍只写 `potential/reused/fresh/nonTargetKnown`，没有 `bySkill/missing`。
- [05-api-design.md](fullstack-design/05-api-design.md#L1279-L1280)：`preview/attribution` 的响应仍写 `{summary{potential,reused,fresh,nonTargetKnown}}`。
- [06-database-design.md](fullstack-design/06-database-design.md#L912)：“预览缓存口径：只读查询既有 `probe_reports.cache_key` … `rule-v1` 计算”。
- [07-backend-implementation.md](fullstack-design/07-backend-implementation.md#L1316)：“`probe_reports.cache_key IN (...)` 查询既有结论；`fresh = potential - reused`”。
- 新口径在 [05-api-design.md](fullstack-design/05-api-design.md#L1288)：“先按空间、对象身份、解析版本及候选 Badcase 选最新完成报告，再按 Skill 汇总；缓存开启时 `fresh=0`，缺报告跳过”。

**现象**

代码的 Agent 模式走 `latest_reports()`，返回 `by_skill` 与 `missing`；只有 legacy rule 模式才回退到 `cache_key`/`rule-v1`。文档把两种模式混成一段，且 05 的表格与 4.9 摘要没有跟上 4.20 的新字段。

**问题**

前端/测试按 05 表格实现，会只读 `potential/reused/fresh/nonTargetKnown`，拿不到 `bySkill` / `missing`；按 06/07 实现，会把“每例最新报告”误做成“按 cache_key 命中”，在对象版本相同但 Skill 不同的报告上给出不同的复用数。`fresh = potential - reused` 也与新口径“缓存开启时 fresh=0、缺报告跳过”不一致。

**预判**

把两种模式分开写：

- Agent / 绑定包模式：`latest_reports`，字段 `potential/reused/fresh/bySkill/missing/nonTargetKnown`；缓存开启时 `reused=已有报告数`、`fresh=0`、`missing=potential-reused`。
- legacy rule 模式：`cache_key` / `rule-v1`，并标明只用于兼容路径。
- 05 表格、4.9 摘要、06 §7.5、07 §5.14 四处同步。

**结论**

待维护者确认。当前状态是“新句在 05:1288，旧表在 05:1279”，同一页就能看到矛盾。

---

### D4（P2，bug）原型选择了“本次重算 Skill”，但没有进入 Run

**位置**

- [harness-evolution.html](ui-prototype-v2/harness-evolution.html#L6098)：`<select id="ev-recompute-skill">` 只在关闭缓存时渲染。
- [harness-evolution.html](ui-prototype-v2/harness-evolution.html#L7363)：change 只写 `EV_STATE.wz.attributionSkill`。
- [harness-evolution.html](ui-prototype-v2/harness-evolution.html#L5016-L5025)：`evMakeRun(cfg)` 不接收 `attributionSkill`。
- [harness-evolution.html](ui-prototype-v2/harness-evolution.html#L6215-L6234)：`ev-wz-start` 调 `evMakeRun` 时也没有传。

**现象**

实测（Chrome 157 headless + CDP）：

1. 登录管理员 → 向导 → 第 4 步关闭缓存；
2. 选择 `harness-trace-review`；
3. 点击“启动自进化”；
4. 新建的 Run 对象 `keys` 为 `id/workspace/title/target/window/createdAt/policy/policyRules/cache/progress/final/models/preparing/failed/worktree/model/clusters`，没有 `attributionSkill`。

**问题**

PR 的核心卖点是“重算时可选择空间内其他 Skill，仅对本次 Run 生效”。原型只演示了选择器，没有演示“选择结果随 Run 持久化”。如果实现同学照原型抄，Run 详情无法显示“本次用了哪个 Skill”，也无法在重试/恢复时还原本次选择。这个缺陷不会抛异常，因此比语法错误更隐蔽。

**预判**

- `evMakeRun` 增加 `attributionSkill: cfg.attributionSkill`（或 `attributionPackageId`）；
- `ev-wz-start` 传 `EV_STATE.wz.attributionSkill || t?.attributionSkill`；
- Run 详情对象归因 step 标题或条件区展示“本次 Skill”；
- 向导切换对象时重置 `wz.attributionSkill`，避免上一个对象的临时选择泄漏到下一个对象。

**结论**

待维护者确认。建议按 bug 修，至少在原型脚本里补齐数据链路。

---

### D5（P2，bug）Run 详情仍是旧缓存口径，与第 4 步数字对不上

**位置**

- [harness-evolution.html](ui-prototype-v2/harness-evolution.html#L4958-L4965)：`cached = run.cache !== false && h%2===0`；`reused = cached && attributed`；`fresh = attributed.length - reused`。
- [harness-evolution.html](ui-prototype-v2/harness-evolution.html#L5411-L5412)：Run 详情“复用缓存 / 本次新增”继续用 `m.reused / m.fresh`。
- [harness-evolution.html](ui-prototype-v2/harness-evolution.html#L5415)：Run 详情仍写“缓存键：工作空间 + bad case + 对象身份/版本 + 策略版本 + 归因模型版本”。
- 新口径在 [harness-evolution.html](ui-prototype-v2/harness-evolution.html#L6093-L6094)：第 4 步用 `hasReport`，缓存开启时“本次新增归因”固定 0。

**现象**

用现有 Run `EV-20261109-01`（`cache=true`）实测：

- Run 详情模型：`potential=9, attributed=8, hasReport=4, reused=3, fresh=5`；
- 第 4 步口径：`复用缓存=4, 本次新增=0, 尚无报告=5`。

**问题**

同一 Run 在“启动前预览”和“运行后详情”给出不同的复用/新增数；Run 详情把“没有报告、本次被跳过”的 5 条算成“本次新增”，而新设计说缓存开启时这些是跳过的。这会让验收者以为 Run 实际重算了 5 条。根因是 `hasReport` 新开了一个布尔，没有替换旧的 `cached`，而 `fresh` 仍按旧公式 `attributed - reused` 计算。

**预判**

- 统一模型：`hasReport` 与 `cached` 至少要有明确关系；`fresh` 在 `run.cache=true` 时应为 0，`missing = potential - hasReport`；
- Run 详情改用 `hasReport`，或直接使用 Run 快照的候选来源 `cached/fresh`；
- 删除 Run 详情里的旧“缓存键”文案，改成“本次选用的 Skill / 最新报告”；
- 第 4 步与 Run 详情共用同一个计数函数，避免两套公式。

**结论**

待维护者确认。

---

### D6（P2，fact）第 4 步展示与设计稿不一致：没有按 Skill 分组、没有零命中禁用

**位置**

- [08-frontend-implementation.md](fullstack-design/08-frontend-implementation.md#L691)：设计要求“按 Skill 分组的已有报告数、缺报告数、预计复用与重算数；缓存开启且零命中时禁用启动”。
- [harness-evolution.html](ui-prototype-v2/harness-evolution.html#L6093-L6098)：只显示总数、当前对象绑定的 Skill 名、总复用/总新增；没有分组。
- [harness-evolution.html](ui-prototype-v2/harness-evolution.html#L6113)：启动按钮始终渲染，没有 `disabled` 条件。

**现象**

- `已有问题报告 attribute-badcases · N 份` 把已有报告都归到**当前对象绑定的 Skill**。实际 `latest_reports` 会返回来源 Skill，可能来自其他包；设计稿要的 `bySkill` 分组在原型里退化成一行。
- 缓存开启且全部候选都无报告时，按 08 应禁用启动（后端也会 `409`），原型仍可点“启动自进化”。当前 fixture 里 `hasReport` 是 `v2Hash` 的奇偶，难以稳定构造零命中，所以这一点是代码阅读结论，未做浏览器复现。

**问题**

- 多 Skill 场景下用户看不到“哪些报告来自 A、哪些来自 B”，无法判断本次复用是否合适。
- 零命中不禁用，会让原型演示一条后端实际会拒绝的路径；评审/验收容易误判。

**预判**

- 用 `bySkill` 分组渲染，例如 `attribute-badcases · 3 份 / harness-trace-review · 2 份`；
- 增加 `missing === potential` 时禁用启动，并给“当前没有可复用报告，请关闭缓存重算”提示；
- 当前对象绑定的 Skill 只作为“重算默认值”，不要作为已有报告的归属标签。

**结论**

待维护者确认。

---

### D7（P3，fact）其余旧文案与结构问题

这些单条不足以单独开讨论点，但会在同一页制造“旧版本残留”：

| 位置 | 现象 | 建议 |
|---|---|---|
| [02-features.md](fullstack-design/02-features.md#L127) | F26 仍写“④ 潜在/复用/新增/历史非该对象四数” | 改成“潜在 / 按 Skill 分组的已有报告 / 缺报告 / 复用 / 重算” |
| [08-frontend-implementation.md](fullstack-design/08-frontend-implementation.md#L790) | 第 4 步展示仍是“统计四数 + 表格” | 与 08:691 统一 |
| [08-frontend-implementation.md](fullstack-design/08-frontend-implementation.md#L779) | Run 详情仍写“关联 Session 显示 `已关联 / 版本未知`” | 新批次 `versionUnresolved=0`；若保留，注明仅历史 Run |
| [02-features.md](fullstack-design/02-features.md#L177-L189) | “对象绑定归因”整节追加在验收口径之后，表格与正文重复 05/07/08 | 要么并入 F26/F27，要么缩成索引并链接到 05/06/07 |
| [README.md](fullstack-design/README.md#L96) | D23 从“2026-11-11，V2 + 详细决策 + 07/06 链接”改成两句概述，丢了日期、理由与引用 | 保留日期与 owning 引用；把新决策单独补一行，不要覆盖原 D23 的可追溯信息 |

**现象 / 问题**

- 02 的 F26 验收口径与 08 的新 Step 4 描述不一致，验收者可能按旧四数验收。
- D23 是决策表，不是功能简介；覆盖后失去“为什么这样定、什么时候定的、去哪里看细节”。
- 02 末尾新增节没有 F 编号，也没有进入 §2 的功能矩阵；它更像 07/08 的摘要，违反“一个事实一个 home”。

**预判**

优先修 F26 与 08:790；D23 至少补回日期和 07/06 链接，避免决策记录退化。

**结论**

待维护者确认。

---

### D8（P3，decision）原型无法表达“历史内联提示词”绑定

**位置**

- [harness-evolution.html](ui-prototype-v2/harness-evolution.html#L7566)：target modal 的 Skill 下拉只列 `v2SkillState().items`。
- [harness-evolution.html](ui-prototype-v2/harness-evolution.html#L7574-L7588)：保存时无条件读取 `v2TgSkill.value` 并写 `attributionSkill`。
- 后端兼容语义：`apps/api/app/db/crud/evolution_targets.py:363` 注释“A legacy inline Skill remains bound until a package is selected”。

**现象**

如果历史对象绑定的是内联提示词（没有 `attribution_package_id`），原型打开编辑框会默认选中 `attribute-badcases`；点保存就把内联绑定覆盖成默认包。原型没有“历史内联提示词”这个选项，也没有只读提示。

**问题**

02 自己写了“保留已绑定内联提示词的读取和历史回放”。原型是 UI 验收基线，照此实现会破坏迁移兼容：用户只是改个版本，就把历史内联 Skill 换成默认包。

**预判**

- target modal 增加“历史内联提示词（只读）”选项，未显式换包时保存不写 `attributionPackageId`；
- 或保存时若原对象无包且用户未改 Skill，不提交该字段；
- 让 `v2BoundTargets` / 详情页能显示“内联”来源。

**结论**

待维护者确认。这条是设计取舍，不一定是本轮必须修，但原型至少不应演示“静默换包”。

## §3 数据流走查：一次“换 Skill 重算”在原型里断在哪

1. **入口**：向导第 4 步关闭缓存 → 渲染 `#ev-recompute-skill`，选项来自 `v2SkillState().items`（[L6098](ui-prototype-v2/harness-evolution.html#L6098)）。
2. **选择**：change 事件写 `EV_STATE.wz.attributionSkill`（[L7363](ui-prototype-v2/harness-evolution.html#L7363)）。
3. **启动**：`ev-wz-start` 调 `evMakeRun`（[L6215-L6234](ui-prototype-v2/harness-evolution.html#L6215-L6234)）。
4. **断点**：`evMakeRun` 只复制 `id/workspace/title/target/window/policy/policyRules/cache/progress`（[L5016-L5025](ui-prototype-v2/harness-evolution.html#L5016-L5025)），没有 `attributionSkill`。
5. **Run 详情**：没有字段可显示“本次 Skill”；仍用旧的 `m.reused/m.fresh` 和 cache_key 文案（[L5411-L5415](ui-prototype-v2/harness-evolution.html#L5411-L5415)）。

所以“仅对本次 Run 生效”在原型里只完成了“选择”这一步；**生效与可追溯都没有落地**。

## §4 导读地图

| 文件 | 阅读范围 | 状态 |
|---|---|---|
| `plans/ui-prototype-v2/harness-evolution.html` | `evRunModel`、向导第 4 步、Skill 库、target modal、启动/change 事件；并用 headless Chrome 走通登录→向导→启动 | ◻ 未通读 7k 行；关键路径已实测 |
| `plans/fullstack-design/02-features.md` | F26、验收段、文末新增节 | ◻ 仅读归因相关段落 |
| `plans/fullstack-design/05-api-design.md` | §4.9、§4.11、§4.20、§10 深链 | ◻ 仅读归因相关段落 |
| `plans/fullstack-design/06-database-design.md` | §4.2/§4.3、§5.1、§7.5、§9 | ◻ 仅读归因相关段落 |
| `plans/fullstack-design/07-backend-implementation.md` | §5.12–5.14 | ◻ 仅读归因相关段落 |
| `plans/fullstack-design/08-frontend-implementation.md` | §9.2、Run 详情 | ◻ 仅读归因相关段落 |
| `plans/fullstack-design/README.md` | D23 行 | 已读 |

## §5 人工验收

已执行：

```sh
git merge-base d33b2c45^1 d33b2c45^2        # 6d473733，等于第一父提交
git diff --stat 6d473733 d33b2c45 -- plans/ui-prototype-v2/harness-evolution.html plans/fullstack-design/
node --check <提取的 8 段 script>             # 8 段内联脚本语法通过
```

原型浏览器实测（Chrome 157 headless，CDP）：

- 页面加载无 `Runtime.exceptionThrown`；
- 管理员登录 → `attribution-skills` → target modal 下拉含 `attribute-badcases` / `harness-trace-review`；
- 向导第 4 步关闭缓存选 `harness-trace-review` 后启动，新 Run 对象无 Skill 字段；
- Run `EV-20261109-01` 详情 `reused=3, fresh=5`，同 Run 第 4 步口径 `reused=4, fresh=0`。

未执行：

- `pnpm lint:docs`、`pnpm verify:docs`、`pnpm verify:flow`：本次只做只读检视，未在 worktree 安装依赖。
- 零命中禁用启动：现有 fixture 难以稳定构造全部无报告，仅做代码阅读判断，已在 D6 标注。

建议维护者按以下顺序复核：

1. `grep -n "identity\|body hash\|cache_key\|rule-v1" plans/fullstack-design/{05,06,07,08}*.md`，确认 D1/D3 的旧句是否还在。
2. 打开原型，重复 §3 的 1–4 步，确认选择器值是否进入 Run。
3. 打开 `EV-20261109-01` 详情与同一 Run 的向导第 4 步，对照 D5 的数字。
4. 检查 05 §4.11 / 06 §5.1 是否补上 `attributionPackageId` 与绑定列。

## §6 分流表

| 发现 | 定性 | 去处 |
|---|---|---|
| 05/06/07/08 同时存在 identity 与 presence 两套关联规则 | fact | 对应 docs 页；按 owning Note 收敛为 presence |
| target CRUD 与 DB 未记录 Skill 包、绑定列、0023a–0031 迁移 | fact | 05 §4.11 / 06 §5.1 / 06 §9 |
| 归因预览 summary 字段与 cache_key/rule-v1 旧口径 | fact | 05 §4.9/§4.20、06 §7.5、07 §5.14 |
| 原型选择的重算 Skill 不进入 Run | bug | 原型脚本 `evMakeRun` / `ev-wz-start` |
| 原型 Run 详情复用/新增数与第 4 步不一致 | bug | 原型 `evRunModel` / Run 详情 |
| 原型无 bySkill 分组、零命中不禁用 | fact | 原型第 4 步 |
| F26/08:790 仍写“四数”；D23 丢日期与链接 | fact | 02 F26、08 Run 详情、README D23 |
| 历史内联提示词绑定在原型中会被静默换包 | decision | owning Note / 05 / target modal |

## §7 文件级分析

### 7.1 `plans/ui-prototype-v2/harness-evolution.html`

- **做对了**：Skill 资源库从“设为生效”改成“查看详情 + 绑定对象”，和“对象绑定 Skill”一致；向导第 4 步新增选择器与“已有报告/尚无报告”文案；target modal 增加 Skill 字段。
- **没闭环**：选择器不进 Run；Run 详情仍是旧 `m.reused/m.fresh` 和 cache_key 文案；第 4 步没有 bySkill 分组与零命中禁用；历史内联绑定无法表达。
- **判定**：UI 方向对，数据链路与同页一致性未完成。若只作为视觉原型可接受，但 PR 描述把它当作“单次重算”的验收基线，就会误导实现。

### 7.2 `plans/fullstack-design/05-api-design.md`

- **做对了**：§4.20 新增 `bySkill` / `missing` 与“最新完成报告”口径；`stats.sessions` 改成“出现所选对象”。
- **没闭环**：§4.9 与 §4.20 表格未同步；§4.11 target CRUD 没有 `attributionPackageId`；`preview/attribution` 表格仍是旧四字段；“关联与缓存键使用后者”仍把关联绑到 `targetRevision`。
- **判定**：同一文件内有新句与旧表，属于“改了一半”。

### 7.3 `plans/fullstack-design/06-database-design.md`

- **做对了**：§4.3 删除部分 cache_key 叙述，改为“复用统计 / 写入方”；§7.5 新增“对象出现”行。
- **没闭环**：§7.5 仍保留“对象进入点 identity”“Session 关联 identity”“cache_key/rule-v1”；§5.1 没有绑定列；新表与新迁移没有文档。
- **判定**：最严重的一处“双口径”，因为同一张表里两行互相否定。

### 7.4 `plans/fullstack-design/07-backend-implementation.md`

- **做对了**：新增 `run_skill` 协议；“关联口径”改成类型+名称。
- **没闭环**：上一行“触发点身份”仍是 identity；§5.14 `preview/sessions` / `preview/attribution` 仍是旧实现；“policy … 归因预览缓存键使用 rule-v1”仍是旧句。
- **判定**：实现描述与新增协议并存，读者无法判断哪条是现行规则。

### 7.5 `plans/fullstack-design/08-frontend-implementation.md`

- **做对了**：Step 2 的“版本出现”改成“对象出现”；Step 4 改成按 Skill 分组/缺报告/重算。
- **没闭环**：Step 2 仍说“body hash 匹配”；Step 4 仍写“统计四数”；Run 详情仍写“版本未知”；Step 4 的零命中禁用未在原型体现。
- **判定**：前端章节是“新标题 + 旧细节”的混合体。

### 7.6 `plans/fullstack-design/02-features.md` / `README.md`

- **做对了**：F26 的 ② 改成整棵树出现；新增“对象绑定归因”叙述；D23 改成对象版本归因。
- **没闭环**：F26 ④ 仍是旧四数；新增节与 05/06/07/08 重复；D23 丢了日期、理由、07/06 链接。
- **判定**：功能层叙事可以，但与契约层没有对齐。

## §8 附：建议的最小修复顺序

如果维护者只想用最小改动消除“回退老版本”的观感：

1. **先修 06 §7.5**：删掉 identity 两行，统一为“类型+名称出现；`targetRevision` 只固定原文/报告/缓存”。
2. **再修 05 §4.9/§4.20 表**：补 `bySkill/missing`，拆“关联 vs 缓存”。
3. **再修 07 §5.12/§5.14**：同步 identity 与 cache_key 两句。
4. **再修 08 Step 2/Step 4/790**：删 body hash，改四数。
5. **原型 D4/D5**：`evMakeRun` 保存 `attributionSkill`；Run 详情改用 `hasReport`，缓存开启时 `fresh=0`。
6. **最后补 05 §4.11 / 06 §5.1 / §9**：target 绑定字段、包表、0023a–0031 迁移。
7. **D23**：补回日期与 owning 链接，不要求恢复旧文全文，但要保留可追溯入口。

---

*本检视为只读分析；未修改被检视文件。行号基于 `main@2f4bce1d`；#554 合入后行号可能移动。*
