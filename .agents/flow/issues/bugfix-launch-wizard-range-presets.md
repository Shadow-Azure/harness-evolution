# 启动自进化向导的时间段支持近 7 天 / 近 30 天 / 近半年快捷预设

[English](bugfix-launch-wizard-range-presets.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-30
milestone: bugfix
depends:
  - m10-05
priority: P2
status: in-progress
scope:
  - plans/ui-prototype-v2/**
  - plans/fullstack-design/**
  - plans/**
  - .agents/**
adr: []
github:
  number: 535
  url: https://github.com/Shadow-Azure/harness-evolution/issues/535
```

## 背景

### 问题场景

2026-11-23，用户反馈「启动自进化」第 1 步的「bad case 时间段」只能手动点两次日期选择器。近 7 天、近 30 天、近半年这类常用窗口每次都要重复选择起止日，既慢又容易把起止日选反。用户希望在原型中先支持三个快捷项，点选后自动填出具体日期，并把诉求、原型修改前后截图和修改方案写进 issue，PR 同时修改设计文档。

当前原型（基线 `main@6d473733`）第 1 步只有两个原生日期输入，默认 `2026-10-01 ~ 2026-11-09`，日期上方没有任何快捷入口：

![原型修改前：启动自进化第 1 步只有两个日期输入，没有时间段快捷项（基线 main@6d473733）](https://github.com/Shadow-Azure/harness-evolution/releases/download/launch-wizard-range-presets-evidence-20261123/before-wizard1.png)

### 现场观察

- 时间段的语义是按 bad case 的 `created_at` 过滤，结束日通常就是今天；常用窗口都可以由「今天」和固定天数/月数直接算出。
- 日期是闭区间，现有校验要求 `from <= to`；快捷项只能减少输入成本，不能改变过滤口径、请求字段或后续 Session 关联规则。
- 原型把演示日期固定在 `V2_TODAY = 2026-11-10`，所有演示数据都围绕这一天；快捷项的「今天」必须跟这个演示日一致，否则截图里的具体日期与页面数据脱节。
- V2 总览页已经有「近 7 天 / 近 30 天 / 近 90 天」分段控件；向导只借鉴「常用区间单选」的信息结构，视觉上改用轻量胶囊 + 浅色选中态，避免把快捷项做成第二条工具栏，也不复用总览的粒度联动。

### 影响

- 不影响后端、API、契约或运行快照；这是第 1 步的输入体验问题。
- 生产 `LaunchWizard.vue` 仍只有两个日期输入；本 issue 先交付可对照的原型与设计契约，生产实现另开切片。

## 目标

- 在启动向导第 1 步的日期输入同一行提供「近 7 天 / 近 30 天 / 近半年」三个胶囊快捷项。
- 点选后把具体 `from/to` 写入日期输入框：结束日为今天（含当天），近 7 天从今天往前 6 天，近 30 天往前 29 天，近半年往前 6 个自然月。
- 当前日期命中某个预设时用浅蓝底和蓝色文字高亮对应胶囊；手动把日期改成其他值后取消高亮，不增加额外的「自定义」状态。
- 保持原有必填、`from <= to` 校验和请求字段不变；把交互写进 V2 设计文档和 08 前端设计文档，作为生产实现的依据。

## 设计依据

- [08 §9 启动向导 Step 1](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/fullstack-design/08-frontend-implementation.md#L669)：时间段 `from/to` 必填、校验 `from <= to`，本 issue 在该行补充快捷预设口径。
- [V2 设计说明 §7.4.1 时间段快捷预设](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/design-v2.md#L232)：记录计算、只填值不锁定、校验不变和可访问性。
- [四步启动向导与启动条件快照](https://github.com/Shadow-Azure/harness-evolution/blob/main/.agents/notes/implemented/feature/2026-11-17-four-step-launch-wizard.md)：第 1 步是唯一条件编辑面，对象/版本/时间段/策略变化都会清空后续预览。
- [V2 原型演示入口](https://github.com/Shadow-Azure/harness-evolution/blob/main/plans/ui-prototype-v2/index.html)：`harness-evolution.html?u=admin&page=evo&demo=wizard1` 直接打开第 1 步，便于同一场景截图。
- [AppSignal Date and time filter](https://appsignal.design/patterns/date-time-filter.html)：预设相对区间单选、当前项有明确选中态、自定义区间与预设分区；本 issue 采用同一信息结构，视觉改为轻量胶囊 + 浅蓝选中态。
- [Grafana 快捷时间范围](https://grafana.com/whats-new/2025-06-17-server-configurable-quick-time-ranges-for-dashboards/)：常用区间优先、入口保持轻量；本 issue 不引入相对范围协议。

## 实现内容

### 原型交互

- 在 `plans/ui-prototype-v2/harness-evolution.html` 第 1 步把三个胶囊与日期输入放在同一行，中间用细竖线分隔；胶囊使用 `role=group`，当前项设置 `aria-pressed`，选中态为浅蓝底 + 蓝色文字 + 描边。
- 新增 `EV_WZ_RANGE_PRESETS` 与日期辅助函数，按原型演示日 `V2_TODAY` 计算具体区间：

| 预设 | 计算 | 原型示例（V2_TODAY = 2026-11-10） |
|---|---|---|
| 近 7 天 | `today - 6` ~ `today` | `2026-11-04 ~ 2026-11-10` |
| 近 30 天 | `today - 29` ~ `today` | `2026-10-12 ~ 2026-11-10` |
| 近半年 | `today - 6 个自然月` ~ `today` | `2026-05-10 ~ 2026-11-10` |

- 点选只更新 `wz.from` / `wz.to`、两个输入框的值和胶囊态，不重建表单，焦点留在原按钮；手动修改日期触发 `change` 后重新计算命中项，未命中任何预设时三个胶囊都不高亮。
- 近半年的月末按目标月最后一天收敛（例如 8 月 31 日往前 6 个月得到 2 月最后一天）；起止日期按闭区间参与过滤。
- 只改客户端展示，不新增请求字段，不改 `from <= to` 校验、Session 关联、潜在匹配口径或缓存键。

原型修改后（同一场景、1500×900 视口、浅色主题、`u=admin&page=evo&demo=wizard1`）：

**近 30 天已选中，日期自动填为 2026-10-12 ~ 2026-11-10**

![原型修改后：点击近 30 天后自动填入 2026-10-12 ~ 2026-11-10](https://github.com/Shadow-Azure/harness-evolution/releases/download/launch-wizard-range-presets-evidence-20261123/after-30d-v2.png)

**近 7 天已选中，日期自动填为 2026-11-04 ~ 2026-11-10**

![原型修改后：点击近 7 天后自动填入 2026-11-04 ~ 2026-11-10](https://github.com/Shadow-Azure/harness-evolution/releases/download/launch-wizard-range-presets-evidence-20261123/after-7d-v2.png)

**近半年已选中，日期自动填为 2026-05-10 ~ 2026-11-10**

![原型修改后：点击近半年后自动填入 2026-05-10 ~ 2026-11-10](https://github.com/Shadow-Azure/harness-evolution/releases/download/launch-wizard-range-presets-evidence-20261123/after-6m-v2.png)

### 设计文档与决策记录

- `plans/ui-prototype-v2/design-v2.md` 新增 §7.4.1，记录计算口径、只填值不锁定、今天取值边界和可访问性。
- `plans/fullstack-design/08-frontend-implementation.md` 的 §9 Step 1「时间段」补充同样的交互口径，作为生产 `LaunchWizard.vue` 的实现依据。
- 新增 Agent Note `2026-11-23-launch-wizard-range-presets`，记录为什么不在服务端传相对区间、为什么不加「自定义」按钮、为什么不用固定 180 天。

## 实施步骤

1. 在原型第 1 步加入胶囊快捷项、日期辅助函数、命中高亮和点击处理。
2. 更新 `design-v2.md` §7.4.1 与 `08-frontend-implementation.md` §9 Step 1。
3. 新增中英成对的 Agent Note，并运行 `pnpm record:i18n -- <pair>` 重录配对。
4. 用同一浏览器场景抓取修改前/后截图，上传到证据 Release，不把截图提交进仓库。
5. 运行语法检查、`pnpm verify:flow`、`pnpm lint:docs`，并检查 PR 标题带 `(#<issue>)`。
6. 创建原型 PR，PR 描述附修改前后截图和验证记录，由人合并。

## 关联 PR

- 原型与设计文档 PR：[#536](https://github.com/Shadow-Azure/harness-evolution/pull/536)

## 依赖与交付边界

- 依赖：m10-05（四步启动向导，已 done）；本 issue 只补第 1 步的时间段输入体验，不改四步状态机。
- 交付边界：`plans/ui-prototype-v2/**`、`plans/fullstack-design/**`、`.agents/**` 与 PR 自检记录。
- 不修改 `apps/web` 的生产 `LaunchWizard.vue`、`apps/api`、`packages/contracts` 或数据库；生产落地另开 issue。
- 截图作为 Release 证据，不进入仓库；不暴露生产运行 ID、Session 内容或凭据。

## 独立验证

```sh
python3 - <<'PY'
import re
from pathlib import Path
html = Path("plans/ui-prototype-v2/harness-evolution.html").read_text()
scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, re.S)
Path(".tmp-proto-main.js").write_text(scripts[-1])
PY
node --check .tmp-proto-main.js
rm .tmp-proto-main.js
pnpm verify:flow
pnpm lint:docs
```

- 浏览器打开 `plans/ui-prototype-v2/harness-evolution.html?u=admin&page=evo&demo=wizard1`（Chrome，1500×900，浅色主题）。
- 初始日期为 `2026-10-01 ~ 2026-11-09`，三个胶囊都不高亮；点击「近 30 天」后输入框变为 `2026-10-12 ~ 2026-11-10`，只有「近 30 天」高亮；点击「近 7 天」和「近半年」分别得到 `2026-11-04 ~ 2026-11-10` 与 `2026-05-10 ~ 2026-11-10`。
- 手动把结束日改成 `2026-11-09` 后，三个胶囊都不再高亮；点击「下一步：关联 Session」仍按原有必填与 `from <= to` 校验执行。
- 截图见上方证据；同一场景下的修改前图片为基线 `main@6d473733`，修改后图片为本 issue 分支。

## 验收标准

- 第 1 步的日期输入同一行出现「近 7 天 / 近 30 天 / 近半年」三个胶囊，默认不选中任何一项。
- 点选后两个日期输入立即变成具体日期，结束日为今天（含当天）；近 7 天、近 30 天、近半年的示例值分别与上表一致，近半年按自然月收敛。
- 当前值命中预设时胶囊高亮并设置 `aria-pressed=true`；手动修改日期后取消高亮；不出现额外的「自定义」按钮。
- 原有必填、`from <= to` 校验、下一步预览和请求字段不变；页面无横向滚动，弹窗高度和按钮位置正常。
- `design-v2.md` 与 `08-frontend-implementation.md` 已写明同一口径，Agent Note 中英成对且配对记录已重录。
- issue 中同时包含修改前截图、修改后截图和修改方案；PR 描述包含同场景、同视口、同主题的 Before / After 证据。
- 最终验收由提出人确认：在提出人确认原型交互符合预期之前，本 issue 不关闭。

## 门禁与 CI

- `pnpm verify:flow`：流程树、依赖、正文章节与状态机。
- `pnpm verify:flow --diff origin/main`：PR 标题带 `(#<issue>)`、issue 资格与 diff scope 覆盖。
- `pnpm lint:docs`：Agent Note 配对、段落换行与文档门禁。
- PR 只改原型与设计文档，不触发 `apps/web` / `apps/api` 的测试；CI 静态 lane 仍需全绿。
- 本 PR 由人合并；不启用 auto-merge。

## 非目标

- 不改生产 `apps/web` 的 `LaunchWizard.vue`，也不要求生产页面在本 PR 同步落地。
- 不改后端、API、契约、数据库、Session 关联、潜在匹配策略或缓存键。
- 不重排第 1 步其他字段，不调整版本组合框、策略单选、向导步骤条或后续步骤。
- 不引入新的日期库、不改变浏览器原生日期控件的可用性，也不做时区/本地化改造。
- 不把快捷预设做成提交后端的相对区间，不增加「自定义」模式，不改变日期闭区间语义。
- 不把截图或生产数据提交进仓库，也不在 issue 中暴露生产运行 ID、Session 内容或凭据。
