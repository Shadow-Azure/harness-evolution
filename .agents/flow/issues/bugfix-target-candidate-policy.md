# 支持按进化对象配置潜在 bad case 来源，统一总览、自动归因与自进化候选范围

[English](bugfix-target-candidate-policy.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-64
milestone: bugfix
depends: []
priority: P2
status: backlog
scope:
  - apps/api/**
  - apps/web/**
  - packages/contracts/**
  - tests/**
  - plans/ui-prototype-v2/**
  - .agents/notes/**
  - docs/**
  - .agents/flow/issues/bugfix-target-candidate-policy*
adr:
  - ../../notes/proposed/feature/2026-11-26-target-candidate-sources.md
github:
  number: 625
  url: https://github.com/Shadow-Azure/harness-evolution/issues/625
```

## 背景

A Skill 上报一条 bad case，随后 C Skill 在同一个根 Session 中执行。用户希望把这条 case 送给 C 的归因 Skill 判断原因。现有空间总览缺少对象级来源规则。向导的时序规则以目标最早出现点为参照，覆盖不了“上报之后才执行目标”。保存 Skill 绑定触发的后台批次还会把策略排除的行加入归因，导致用户在向导里看到的范围和后台实际处理的范围不同。

## 目标

从被归因对象 C 的视角配置候选来源。上报记录保留原来的来源 A 和 `self` / `discovery` 类型。同一 case 可以成为多个对象的候选，是否由某个对象造成，交给该对象版本的归因报告判断。

## 前端原型对比

| 修改前 · 填完基础信息直接新增 | 修改后 · 第一步填基础信息，点击下一步 |
| --- | --- |
| ![修改前 · 填完基础信息直接新增](https://raw.githubusercontent.com/Shadow-Azure/harness-evolution/8a7f30f2c03609ac22d41c30214f5859e6f1074d/plans/ui-prototype-v2/evidence/candidate-rules/before-create.png) | ![修改后 · 第一步填基础信息，点击下一步](https://raw.githubusercontent.com/Shadow-Azure/harness-evolution/8a7f30f2c03609ac22d41c30214f5859e6f1074d/plans/ui-prototype-v2/evidence/candidate-rules/after-create.png) |

| 第二步 · 同尺寸弹窗内配置候选规则 | 已有对象 · 按来源卡片查看上报记录 |
| --- | --- |
| ![第二步 · 同尺寸弹窗内配置候选规则](https://raw.githubusercontent.com/Shadow-Azure/harness-evolution/8a7f30f2c03609ac22d41c30214f5859e6f1074d/plans/ui-prototype-v2/evidence/candidate-rules/create-rules.png) | ![已有对象 · 按来源卡片查看上报记录](https://raw.githubusercontent.com/Shadow-Azure/harness-evolution/8a7f30f2c03609ac22d41c30214f5859e6f1074d/plans/ui-prototype-v2/evidence/candidate-rules/source-reports.png) |

**来源名称下拉框**　每行左侧为上报对象，右侧两列是所选时段内的上报数。

![来源卡片内的下拉框与 self、discovery 计数](https://raw.githubusercontent.com/Shadow-Azure/harness-evolution/8a7f30f2c03609ac22d41c30214f5859e6f1074d/plans/ui-prototype-v2/evidence/candidate-rules/source-counts.png)

[下载单文件交互原型](https://github.com/Shadow-Azure/harness-evolution/blob/8a7f30f2c03609ac22d41c30214f5859e6f1074d/plans/ui-prototype-v2/harness-evolution.html?raw=true)。在浏览器打开下载的 HTML，在地址末尾追加 `?u=admin&page=overview&tab=targets&demo=candidate-rules`，进入 C 的「候选规则」，点来源 A 卡片中的「查看 badcase」。

## 设计依据

现行关联、进入点及比较口径见[数据库设计 §7.5](../../../plans/fullstack-design/06-database-design.md#75-v2-口径空间--触发点--潜在--归因三态)，预览与启动契约见[API 设计 §4.20](../../../plans/fullstack-design/05-api-design.md#420-自进化预览与启动v2)。本提案扩展对象级候选策略及其使用入口。

## 实现内容

1. **新增对象分两步。** 总览和自进化配置页的新增入口均先校验基础信息，再在同一尺寸的弹窗进入候选规则。两步固定标题、步骤导航和底部操作区，仅切换中间表单。第二步为单栏配置。用户可确认默认策略或配置来源。最后点「保存进化对象」一次提交对象、归因 Skill 绑定及规则。上一步保留两步草稿，取消不创建对象、不触发批次。已有对象点「编辑」直接保存基础信息。对象卡片显示生效策略，通过「候选规则」独立修改，普通成员可查看，管理权限控制写入。
2. **按来源精确匹配。** 提供默认、默认加自定义、仅自定义三种模式。来源键为上报对象类型（Skill / Agent）和名称，名称下拉框按当前工作区的 bad case 上报对象去重，只能从所选类型已上报的名称中选择。切换 Skill / Agent 后重新选名。每行把所选时间范围内的 self 和 discovery 数量分两列右对齐，零值显示 0。下拉框宽度限制在当前来源卡片内。来源无需先登记为进化对象，可以选择目标自己。每条来源至少勾选一种上报类型，自定义模式至少有一条有效来源。
3. **按每次执行判断。** 来源规则可以要求目标在 case 锚点之前、之后，或同一根 Session 执行过即可。比较所有可定位的目标执行，先后必须严格，同一触发点不满足任一方向。显式顺序规则需要真实锚点和可比较的执行坐标；仅有后处理锚点或顺序未知时展示原因。同 Session 规则只要求目标出现。保留已有默认策略的同名 self 与后处理语义。
4. **逐来源查看上报。** 每张来源卡片在上报类型右侧提供「查看 badcase」。按该卡片当前选择的来源和上报类型，查询同一工作区、所选时段的 bad case 表。已有对象在右侧显示结果，新增流程用临时弹窗，返回保留草稿。列表支持类型、标签和无标签筛选，多选标签取并集。列表筛选只影响显示。缺少轨迹锚点的上报也可查到。候选匹配阶段再判断执行顺序，多条规则命中同一 case 时对同一对象版本只计一次。
5. **共用已生效的规则。** 总览、自动归因、向导和正式运行使用同一个匹配器。后台批次只消费入选行。运行和批次记录所用规则版本、匹配原因及坐标，以便追溯历史。规则调整可移出当前候选，已有报告仍可查阅。历史对象缺少规则时按默认策略读取。

## 实施步骤

1. 定义策略及版本、默认兼容、权限、校验、保存、上报来源枚举、分类型计数及逐来源查询契约，更新迁移及生成类型。
2. 给共享匹配器增加来源身份、执行实例匹配及命中证据，接入批次和运行快照。
3. 接入两个新增入口、对象卡片、逐来源上报列表及向导回显，覆盖取消、重试及历史读取。

## 依赖与交付边界

[#582](https://github.com/Shadow-Azure/harness-evolution/issues/582) 讨论空间级 label 输入范围。若共同启用，先满足工作空间及其输入范围，再应用对象级规则。规则保存后是否立即扫描历史、回扫多久，以及缓存复用的具体条件，留待详细设计确认。标签示例使用原型数据，接入时需明确上报标签字段。

## 独立验证

打开上方原型，以 A、B、C 示例轨迹验证下列结果。实现阶段使用相同 fixture 驱动 API 和浏览器测试，并断言自动批次收到的具体 case ID。

## 验收标准

- [ ] 新增对象只有在第二步确认后才生效。取消或提交失败均不产生半成品对象或后台批次。已有对象编辑和规则编辑两个入口分别可用。
- [ ] 桌面和窄屏中名称列表均位于卡片左右边界内，名称、self、discovery 三列对齐。演示数据中 Skill A 显示 3 / 2，Agent ReviewBot 显示 0 / 1。
- [ ] 在 C 的 A 卡片勾选两类上报并点击查看，列表展示 A 的 5 条记录，含缺少锚点的 BC-1071。添加 B 后查看该卡片只显示 B 的 2 条；查看、筛选及返回均不提交规则。
- [ ] `A1 → B1 → A2 → B2`，A 只选自己的 self 且同 Session 即可时，纳入 A1 和 A2 各自的 self。改为“目标在锚点之后执行”时，仅 A1 的 self 入选，证据为 A2。
- [ ] `A1 → C1`，C 配置来源 A 且要求目标后执行时，A1 的上报成为 C 的候选。`C1 → A1 → C2` 中后执行证据为 C2，多条规则同时命中只计一次。
- [ ] 同名不同类型的来源、未选中的上报类型、无真实锚点、其他 Session 或空间不能误命中相应自定义规则。仅可选择本空间有历史上报的同类型对象。时段内某类型无上报时显示 0。
- [ ] 同一空间、对象版本、窗口、规则版本及数据快照下，总览候选、自动批次和运行的入选 ID 一致。移出后可查历史报告和原批次的规则快照。

## 门禁与 CI

实现 PR 执行 `pnpm contract:check`、`pnpm test:api`、`pnpm typecheck:web`、`pnpm test` 和对应的 `pnpm test:e2e` 用例。流程变更运行 `pnpm verify:flow`。

## 非目标

本期范围为候选筛选。上报协议、正式归因结论、生产数据回放和历史报告重算策略单独处理。
