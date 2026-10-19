# AGENTS.md — 文档标准

定义 `docs/` 树结构、层级与门禁；规则须机械校验，人只判断。

## 层级：一个事实一个 home

| 层 | 职责 | 不许放 |
|---|---|---|
| 根 `AGENTS.md` | 常驻指令：约束 + 命令清单 + 链接到 home | 故事、示例、从 home 复述的内容 |
| `docs/README.md` | 文档地图：登记 `docs/` 下每一篇常驻文档 | 正文知识 |
| `docs/architecture.md` | 有序地图：组成、数据流、关键决策点 | 决策理由（→ Agent Note）、逐 API 细节 |
| `docs/development.md` | 贡献者上手、日常循环、门禁摘要 | 会漂移的逐项清单（→ `package.json` scripts） |
| `docs/review.md` | PR 检视工作流与分流规则 | 具体 PR 的检视记录（→ `plans/`） |
| `docs/charter.md` | 实验与自进化协议 | 操作步骤（→ development.md） |
| `docs/metrics.md` | 指标定义与记录要求 | 单次实验结果（→ `research/experiments/`） |
| `docs/i18n/README.md` | 双语配对契约 | 翻译教程 |
| `docs/postmortem/` | 事故复盘——全库唯一允许叙事的层级 | 一般性设计讨论 |
| Agent Notes（`.agents/notes/`） | 决策记录：为什么、放弃了什么 | 现状描述（→ docs） |
| `.agents/flow/` | roadmap / milestone / issue 工作文件 + 流程契约 | 决策理由（→ Agent Note） |
| `plans/` | PR 检视与实现计划工作稿，语料之外 | 常驻事实、决策记录 |

放置口诀：bug → postmortem；理由 → Agent Note；步骤 → development.md；现状 → 对应 docs 页；常驻规则 → 根 AGENTS.md（附理由链接）；检视过程 → `plans/`。

## 写作规则

- **写现状，不写变更史**：避免"以前/现在/不再"；变更故事进 commit、Agent Note 或 postmortem。
- **双语成对**：常驻文档中英三件套成对合并，改任一侧最小修补另一侧并重录（契约：[i18n/README.md](i18n/README.md)）。
- 段落一行到底（soft-wrap），表格与代码块保持原样（红门禁：verify-md-wrap）。
- 文档内代码示例必须可用；类型声明用 ` ```ts type-equiv ` 围栏，与源码逐字等价（manifest 1:1）。
- 普通 ` ```ts ` 围栏会被真实编译；未验证的示例不要写成可编译围栏。
- 导出面须带文档注释（verify-export-docs）；导出函数写 `@param` 与 `@returns`。
- 每个非平凡变更在同一 PR 新增或更新至少一条 Agent Note。
- 常驻文档受词数预算约束（[scripts/doc-budgets.manifest.json](../scripts/doc-budgets.manifest.json)），常驻即登记；超限处置：搬层 → 压缩 → 提预算（须在 PR 说明）。

## 门禁

```sh
pnpm lint:docs    # doc-quick：索引、Note、预算、段落换行、配对、术语、type-equiv、导出注释、源码引用
pnpm verify:docs  # doc-sync：上述 + ts 围栏编译 + 死链 + 门禁自测试
```

叶子清单与组合见 [scripts/run-gates.mjs](../scripts/run-gates.mjs)；CI 静态 lane 内嵌 doc-sync（见 [.github/workflows/ci.yml](../.github/workflows/ci.yml)），不存在"CI 忘配文档门禁"的路径。
