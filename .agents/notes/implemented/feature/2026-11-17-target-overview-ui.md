# Agent Note: 进化对象总览前端视角

Status: implemented

[English](2026-11-17-target-overview-ui.en.md) | 中文

## Problem

总览页原本只有 bad case 视角：来源、趋势和列表都围绕上报来源组织，`?tab=targets` 被显式降级回 `tab=cases` 并提示「M11 提供」。m11-03 已交付对象总览的四个只读端点，但页面还缺一个与原型对齐的视角：对象统计、三态趋势、两类分布、每页 5 个的对象侧栏、单对象独立版本/时间分析卡，以及按对象/来源/状态/时间筛选的潜在 case 列表。这里的难点不是多画几个组件，而是把「共享时间窗」与「单对象独立筛选」放进同一份 URL 状态，并让数字口径与 API 的 `(badCaseId, targetVersion)` 行级计数一致。

## Decision

- 双视角共享 `tab`、`range`/`from`/`to` 与 `grain`；切换 Tab 只重置 `page`，不重置时间窗与粒度。`?tab=targets` 现在是合法状态，旧的降级提示与「M11 提供」禁用态删除。对象视角另外拥有 `targets`（趋势对象多选）、`states`（趋势三态）、`tpage`（对象侧栏页）、`ctarget`/`csource`/`cstate`/`cfrom`/`cto`/`page`（潜在 case 列表）与 `dtarget`/`dversions`/`dfrom`/`dto`/`dlimit`（单对象卡）；全部经 `overviewUrl.ts` 解析与规范化，非法值回落，刷新可恢复，`overviewQuery("cases")` 的既有规范形保持不变。
- 对象侧栏需要完整排序集合，而列表端点单页最多 50 条；`listAllOverviewTargets` 先取 `pageSize=50`，再按 `total` 补页，页面在客户端按 5 条分页。这样侧栏、对象多选与单对象选择器共用同一份 evolvable 排序，不用把 `/evolution/targets` 的配置列表混进展示数据。趋势、列表与详情仍各自请求，保持 m11-03 的四端点独立读语义。
- 趋势三态 chip 在客户端切换，不把 `states` 传给 `/targets/trend`：API 的 `states` 过滤会把未选状态的计数清零，chip 上的总数就会随筛选变化；客户端保留完整桶数据再按所选状态求柱高，chip 数字始终是「当前对象与时间窗内该状态的总数」。至少保留一个状态，全选时回写空 `states` 以保持 URL canonical。潜在 case 列表的 `cstate` 是独立服务端筛选，与趋势选择互不影响。
- 两块分布都从已有响应推导，不新增请求：关联 Session 分布用完整对象列表的 `sessions`（一个 Session 可同时出现在多个对象下，tooltip 明说），潜在 case 分布用趋势桶的 `byTarget` 按对象求和后按三态分段；柱长分别按最大 Session 数与最大潜在数归一。列表来源筛选的选项复用 bad case summary 的 `objects`（页面在双 Tab 都保留 summary 请求），避免为了几个下拉再跑一次 matcher。
- 单对象卡把 `dtarget` 之外的筛选独立传给 detail 端点：显式版本走 `dversions`，否则 `dlimit` 映射 `5|10|20|0(全部)`；`dfrom`/`dto` 缺省时跟随共享窗口，设置后显示「跟随总览」清除。卡片只改自己的 query key，趋势与列表不随版本或对象卡时间变化；切对象时清空显式版本，避免版本名跨对象复用。
- 对象维护入口复用 `TargetFormDialog` 与 `useEvolutionTargets`，权限按空间角色 `canManageWorkspace`（global/space admin）判断，而不是全局用户角色；新增/编辑/移除成功后失效 `["ws", wid, "overview"]` 前缀并同步修正 URL 中已被移除的 `targets`/`ctarget`/`dtarget`。移除仍走服务端 409（有进行中 run）并显示在区块内。
- 潜在 case 行展示 `badCaseId`、`objectName@version`、来源、三态、上报时间、Session、归因报告 ID 与分类；ID 链接打开错误详情 `?case=&tab=desc`，归因 ID 打开 `?case=&tab=attr&at=`。分类只在 attributed 行有值，未归因/非该对象显示 `—`，不把「未分析」写成「非该对象」。
- 工作空间壳把 `main` 固定为视口高度并裁掉溢出，概览页自己成为滚动容器（`height: 100%; overflow-y: auto`）；否则页面越高，单对象卡与潜在 case 表越会落在视口之外且无法滚到。移动端仍交给文档流滚动。
- 视觉按 `plans/ui-prototype-v2/harness-evolution.html` 的对象视角实现：`TargetsOverview` 组合统计条、筛选条、趋势卡、对象侧栏、分析卡与潜在 case 表；三态色沿用原型的 green/orange/faint，柱与分布用自研 SVG 和纯函数 `stackSegments`，不引第三方图表库。

## Alternatives considered

- **把对象视角做成独立路由**：原型是总览页的二级 Tab，独立路由会丢失共享时间窗和浏览器后退语义；拒绝。保留 `?tab=` 与同一页面状态。
- **趋势 `states` 交给服务端过滤**：请求更少、实现更直接，但 chip 总数会随筛选变化，点掉「未分析」后该 chip 自己也变 0，无法再点回来；拒绝。服务端 `states` 仍用于潜在 case 列表。
- **对象侧栏只请求 5 条并另取配置列表补名称**：会出现排序口径两套（evolvable vs 配置顺序），侧栏与多选项也对不上；拒绝。一次补页取全量，客户端分页。
- **单对象卡复用共享时间窗与对象选择**：原型明确要求对象、版本、时间三者独立，否则无法回答「这个版本在这段时间的表现」；拒绝。detail 端点已支持独立窗口与版本。
- **新增图表库或引入 Element Plus 图表组件**：违背 m11-04 非目标与 bundle 约束；拒绝。沿用 overview 的 SVG 纯函数，并为三段堆叠补 `stackSegments` 单测。
- **把来源筛选选项从当前列表页反推**：列表翻页后下拉选项会漂移；拒绝。复用 summary 的全空间来源集合。
- **移除对象时只依赖列表刷新**：URL 里的 `targets`/`ctarget`/`dtarget` 会指向不存在的 id，趋势和详情请求持续 422/404；拒绝。删除成功后立即从 URL 清理。

## Consequences

- 目标视角首屏会并发 4 个 overview 读请求（完整对象列表、趋势、潜在 case、单对象详情）加共享 summary；对象侧的 matcher 成本仍是 m11-03 的线性成本，前端不缓存跨页结果。切换 Tab 时趋势/列表/来源请求被禁用，避免在 bad case 视角继续算对象。
- 侧栏的「每页 5 个」是客户端分页，`tpage` 只影响切片，不会减少对象列表请求；若未来单空间对象数很大，需要把侧栏改回服务端分页并把完整集合拆成独立的选项端点。
- URL 键较多，但每个都只在非默认时出现；`page` 在两个 Tab 共用（切换 Tab 重置为 1），对象侧栏用独立的 `tpage`，避免与潜在 case 列表互相踩页码。
- 趋势 chip 的客户端筛选意味着「柱高之和」不等于列表总数（列表还有来源、状态、独立时间过滤），页面用文案与 tooltip 说明，不把两个数字硬凑相等。
- 来源下拉来自 bad case summary，可能包含当前对象筛选下不会出现的来源；这是稳定选项与精确选项的取舍，选中后列表可能为空并显示筛选空态。
- 对象维护复用 target 配置表单，因此概览页会加载该表单的 Element Plus 依赖；Vite 已把它拆成共享 chunk，不进入首屏同步入口，`verify:bundle` 覆盖该边界。
- 对象侧栏的版本显示 `versions[0]`：API 返回的是「窗口内已观测版本并上 defaultRef」的自然降序集合，不单独给 defaultRef，所以页面不能保证显示配置的基线；选择最高已观测版本是可解释的近似。
- 目标列表 API 不返回 case 描述，列表末列用归因分类替代原型的「问题现象/描述」，标题仍放在首列；这是数据契约边界，不是视觉缺口。
