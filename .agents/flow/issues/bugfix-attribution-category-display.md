# Session 概览将流程、上下文归因误标为错误，四个页面的分类标签不一致

[English](bugfix-attribution-category-display.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-75
milestone: bugfix
depends: []
priority: P2
status: in-progress
scope:
  - attribute-badcases/SKILL.md
  - attribute-badcases/make_probe_report.py
  - attribute/README*
  - apps/api/app/api/problems.py
  - apps/api/app/service/bad_cases/**
  - apps/api/app/service/problems/schemas.py
  - apps/api/tests/**
  - apps/web/src/components/bad-cases/**
  - apps/web/src/pages/errors/**
  - apps/web/src/pages/evolution/**
  - apps/web/src/pages/overview/components/PotentialCaseTable*
  - apps/web/src/router/deepLink*
  - apps/web/src/utils/**
  - packages/contracts/**
  - tests/e2e/**
  - .agents/flow/issues/bugfix-attribution-category-display*
  - .agents/notes/implemented/**
adr: []
github:
  number: 631
  url: https://github.com/Shadow-Azure/harness-evolution/issues/631
```

## 背景

同一份 `flow` 报告在 Session 概览显示「是问题-错误」，点开归因详情却显示「流程」。`context` 也被概览误标为「错误」。以下结果来自 `main@cc5b7726`，五份合成报告均使用 `attributed`，写入本地 SQLite 后读取列表与详情数据，再渲染对应的 Vue 组件。

| `attribute_type` | 归因详情页 | 自进化「对象归因」步骤 | Session 概览问题列表 | 空间概览「潜在 bad case」归因分类 |
| --- | --- | --- | --- | --- |
| `model` | 模型问题 | 模型 | 是问题-模型问题 | `model` |
| `prompt` | prompt缺失某些提示词 | prompt | 是问题-prompt缺失某些提示词 | `prompt` |
| `error` | 错误 | 错误 | 是问题-错误 | `error` |
| `flow` | 流程 | 流程 | **是问题-错误** | `flow` |
| `context` | 上下文 | 上下文 | **是问题-错误** | `context` |

另外，Skill 将遗漏、错误、多余和有歧义的指令都归入 `prompt`，详情页和列表却把它缩小为「缺失某些提示词」。空间概览直接输出 API 英文值。[Skill 分类说明](https://github.com/Shadow-Azure/harness-evolution/blob/cc5b7726f30f15fe75ba4f89552a2454f48c8c7b/attribute-badcases/SKILL.md#L274-L288) · [空间概览分类列](https://github.com/Shadow-Azure/harness-evolution/blob/cc5b7726f30f15fe75ba4f89552a2454f48c8c7b/apps/web/src/pages/overview/components/PotentialCaseTable.vue#L373-L382)

## 目标

同一份报告在四个入口都能看出同一个问题类别。建议统一类别名称为「模型问题、提示词问题、错误、流程、上下文」，Session 列表可保留「是问题-」前缀。

归因 Skill 生成的报告 ID 应适合现有 64 字符字段，相同输入能复算相同的 ID。已保存的长 ID 报告应可从列表和深链按原始 ID 打开。

## 设计依据

[前端设计 §5 Session 浏览器、§7.3 归因 Tab、§10 运行详情](../../../plans/fullstack-design/08-frontend-implementation.md)。报告级 `conclusion` 表示当前对象是否应负责，`attribute_type` 表示已归因问题的类别，两者分别展示。

## 实现内容

写库与详情 API 已能区分五类。Session 列表的 `analysis.attributeType` 也正确，但 `_display_state()` 只单独处理 `model` 和 `prompt`，把 `flow`、`context` 都映射成 `analyzed_issue_error`。列表组件依据 `displayState` 绘制徽标。这个错误会让用户在进入详情前误判问题性质。[后端映射](https://github.com/Shadow-Azure/harness-evolution/blob/cc5b7726f30f15fe75ba4f89552a2454f48c8c7b/apps/api/app/service/bad_cases/service.py#L110-L116) · [列表徽标](https://github.com/Shadow-Azure/harness-evolution/blob/cc5b7726f30f15fe75ba4f89552a2454f48c8c7b/apps/web/src/components/bad-cases/badCaseDisplay.ts#L23-L34) · [详情页分类](https://github.com/Shadow-Azure/harness-evolution/blob/cc5b7726f30f15fe75ba4f89552a2454f48c8c7b/apps/web/src/pages/errors/components/attributionDisplay.ts#L30-L39)

## 实施步骤

1. 在后端 `DisplayState` 增加 `analyzed_issue_flow`、`analyzed_issue_context`，以五类显式映射生成列表状态，保留已有状态值。运行 `pnpm contract:generate`，同步 OpenAPI 和前端生成类型。
2. 前端以 API 分类类型为键建立一份完整的标签映射。归因详情、对象归因步骤和潜在 bad case 分类列直接复用；Session 列表沿用状态前缀，从同一份映射取类别名。为新增的两种列表状态接入相应徽标。
3. 参数化验证五种类别从 SQLite 读回的详情分类、列表状态和四个页面可见文本。另覆盖 `non_target` 和 `inconclusive`，避免空分类回退成「错误」。

## 依赖与交付边界

沿用现有数据库字段 `probe_reports.attribute_type` 和报告脚本。脚本可用 `unknown` 描述未定类别；`attributed` 必须给出五类之一。对 `non_target` 和 `inconclusive`，业务分类列为 `NULL`。修复可直接应用于已有五类报告。

## 独立验证

使用五个 `attributed` 合成样本，每种类别一个。读取同一份报告的详情 `category`、Session 列表 `analysis.attributeType` 与 `analysis.displayState`，再打开表中四个入口比较标签。以 `flow` 为例，当前读回 `flow / flow / analyzed_issue_error`，预期第三项为 `analyzed_issue_flow`，列表呈现「是问题-流程」。

## 验收标准

- 五类在四个入口逐项匹配目标标签。`flow` 和 `context` 在 Session 概览分别显示「是问题-流程」「是问题-上下文」。
- `prompt` 在四处均表达「提示词问题」，可涵盖缺失、错误、多余和歧义。空间概览对五类均展示中文。
- 空分类不出现五类问题徽标；归因详情仍能区分「非该对象问题」和「归因证据不足」。后端和前端的参数化回归进入 CI。

- 使用长对象名和 64 字符的 bad case ID 生成并复核报告。用历史复合 ID 验证分页、空间详情、兼容读接口与浏览器直达。

## 门禁与 CI

`pnpm test:api`、`pnpm test:web`、`pnpm typecheck:web`、`pnpm contract:check`。

## 非目标

数据库迁移、生产数据回填、历史报告重算及归因模型判定逻辑调整均另行立项。
