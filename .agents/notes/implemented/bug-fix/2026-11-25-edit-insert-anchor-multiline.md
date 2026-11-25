# Agent Note: edit 的 insert_after 锚点契约统一为可跨行文本块

Status: implemented

[English](2026-11-25-edit-insert-anchor-multiline.en.md) | 中文

## Problem

生产 full run `01M885592456VVK5B68DSMRKTE` 在第 6/7 步「迭代优化」的第 3/10 轮 patch 阶段失败：`claude-code edit submission failed validation`。提交文件已被正常解析（`submissionParsedBy=json5`、`submissionParseFailures=0`），但 `EditPlan.model_validate()` 拒绝了第 7 条（0-based `edits.6`）`insert_after`：`target must be a single-line substring`。该 target 是 `### 验收与回归` 模板的 4 行文本块（158 字符），在目标 `SKILL.md` 中恰好出现 1 次——模型按它被告知的契约（prompt 与派生 schema 只说「锚文本必须存在且唯一」）做了正确的事，validator 却执行一条未公开、与设计文档 07 §5.5.4 不一致的更严格规则。edit 是单次调用、校验失败不重试，这条只活在 validator 里的隐藏规则直接把整轮打死；同 release 的第 1、2 轮 edit 成功，说明是模型输出形态差异撞上契约不一致，而非部署回归。

## Decision

`insert_after` 的锚点契约统一为「文件内存在且唯一的文本片段，可以跨行」。模型侧删除 `EditOp._validate_op_fields()` 对含 `\n`/`\r` target 的拒绝（#494 引入的单行规则），其余约束（append 禁 target、delete 禁 content、content 非空与行数上限等）原样保留。应用侧把 `_insert_after_text()` 重写为「整段唯一匹配 + 块末行之后插入」：插入点在 target 自身结尾换行（`\r\n`/`\n`/`\r`）之后，否则在匹配块末字符所在行的下一个行终止符之后，EOF 无终止符时补 `\n`；插入行沿用该终止符风格（`\r\n` 保持 `\r\n`；bare `\r` 锚行字节不动，插入行用 `\n`）。`text.count(target)` 的 0 次 → `skipped_anchor_missing`、>1 次 → `error`（ambiguous）分支原样保留，单行 target 的输出与旧实现逐字节一致。契约同步写进模型可见面：`_edit_prompt()` 的锚点行改为「锚文本必须是文件内唯一出现的文本片段，可跨行；insert_after 把 content 插到该片段末行之后」，07 §5.5.4 的执行流 bullet 与 json5 示例注释同步。回归测试覆盖 4 行块锚点的校验与应用、单行逐字节（行中/行尾/EOF 无终止符/bare-`\r`/CRLF）、块锚缺失与多义、CRLF 块插入，以及生产计划形状的 8 条编辑合成 replay（不含生产原文）。

## Alternatives considered

- **给 edit 加字段级反馈重试**：analyze 有 `feedback_prompt()` 重试，edit 没有；加重试要改 `edit_workspace()` 的单次调用语义与 run 状态机，成本远超本缺陷的面，且正确契约根本不该被 validator 藏起来。拒绝。
- **在 prompt 里解释「target 不能含换行」**：把隐藏规则公开化而不是修掉它。多行块是模型自然、唯一、合法的锚点选择，靠 prompt 压制只会逼出更脆弱的绕法，契约继续与 07 §5.5.4 矛盾。拒绝。
- **放宽为允许多 anchor（取首个匹配）**：破坏 #494 以来的「锚存在且唯一」确定性契约，应用结果依赖匹配顺序、不可审计。拒绝；唯一性检查原样保留，多行 target 不绕过它。
- **只修观测（把 `AgentProviderError.detail` 透传进 `ConfigError`）**：能让 run 页显示 `edits.6` 的字段级原因，但修不了「合法计划被拒」本身；观测缺口另记为欠账，不在本方案内扩大修改面。拒绝。

## Consequences

- 生产计划形状（8 条编辑、4 行块锚点、单条 content ≤ 28 行）现在通过 `EditPlan.model_validate()` 且全部 `applied`、只改目标文件；单行 `insert_after` 无行为变化，四 op 精确内容与 `test_insert_after_last_line_without_newline` 等既有逐字节断言全部保持。
- schema 表达不了的条件约束必须进 prompt：派生 JSON Schema 表达不了「某字段取某值时另一字段必须怎样」的条件语义，Pydantic validator 是唯一执行点，调用方 prompt 必须把每条语义约束写成正面向契约，否则就会出现「规则只存在于 validator」的结构性缺口。
- `ConfigError` 转换丢弃 `AgentProviderError.detail` 的观测缺口仍在：`_fail_patch_generation()` 只拿到 `str(error)`，run 页与 job 只显示泛化 message，字段级原因只能从残留 `edits.json5` 复现；修复它属于独立小改动，不在本次范围。
- 三个 anchored op（`replace`/`insert_after`/`delete`）的锚语义完全一致：全文唯一子串匹配，`insert_after` 不再有单行特例；模型拒绝的多行锚由「非法」变为「合法锚点」，坏计划在落盘前失败、应用结果确定可重放的性质不变。
