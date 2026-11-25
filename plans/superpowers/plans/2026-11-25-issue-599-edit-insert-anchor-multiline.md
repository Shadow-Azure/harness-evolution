# edit 多行 insert_after 锚点实现计划（#599）

> **For agentic workers:** this plan follows the superpowers task-by-task style; the linked issue `.agents/flow/issues/bugfix-edit-insert-anchor-multiline.md` is the implementation contract. Every interactive question is answered from `plans/fullstack-design`, not by asking the user.

**Goal:** `insert_after` 的锚点契约统一为「文件内存在且唯一的文本片段（可跨行）」，content 插入在匹配块末行之后；单行 target 输出与现状逐字节一致；prompt、派生 schema 说明、设计文档与 validator 表达同一契约。

**Architecture:** `EditOp`（Pydantic 单一事实源）删除单行拒绝；`edits.py` 应用器改为整段唯一匹配 + 块末行之后插入（沿用 `text.count` 的缺失/多义分支）；`_edit_prompt()` 把可跨行契约写进模型可见文案；07 §5.5.4 同步；回归测试覆盖多行块、单行逐字节一致、CRLF、缺失与多义。

**Scope:** `apps/api/app/third_party_api/ai_agent/edits.py`、`apps/api/app/service/evolution/patch_source.py`、`apps/api/tests/test_edit_plan_applier.py`、`apps/api/tests/test_ai_agent_claude_code.py`（如有 single-line 断言）、`plans/fullstack-design/07-backend-implementation.md`、`plans/**`、`.agents/flow/issues/bugfix-edit-insert-anchor-multiline*`、`.agents/notes/implemented/bug-fix/2026-11-25-edit-insert-anchor-multiline*`。不改 `claude_code.py` / `submission.py` / 工具面 / 预算 / 超时 / 前端。

## 交互问题的设计答案

| 问题 | 答案来源 | 决定 |
|---|---|---|
| 多行 target 的插入点在哪？ | issue 目标 2 + [07 §5.5.4](../../fullstack-design/07-backend-implementation.md#554-edit-指令式-patcheditplan--editspy) | 匹配块末行之后；确定性、可重放 |
| target 自身以换行结尾时怎么办？ | issue 实现内容 2 | 以该换行之后为插入点，不额外补终止符 |
| 插入行的换行风格？ | issue 实现内容 2 | 沿用锚块末行现有风格：`\r\n` 或 `\n`（bare `\r` 回落 `\n`，与现状一致） |
| 单行 target 是否改变输出？ | issue 目标 2 | 否，逐字节一致；`test_insert_after_last_line_without_newline` 等既有用例保持通过 |
| 锚缺失 / 多义如何处理？ | issue 实现内容 2 + #494 契约 | 沿用 `text.count(target)`：0 次 → `skipped_anchor_missing`，>1 → `error`（`anchor is ambiguous`） |
| 是否保留唯一性/预算/scope 限制？ | issue 非目标 | 全部保留；不允许用多行 target 绕过唯一性检查 |
| edit 是否增加反馈重试？ | issue 非目标 + 07 §5.5.3 | 不增加；单次调用、失败即终止的语义不变 |
| prompt 里怎么写锚点契约？ | issue 实现内容 3 + 07 §5.5.3「调用方 prompt 必须把 schema 表达不了的语义约束说清楚」 | 「锚文本是文件内唯一出现的文本片段，可跨行；insert_after 插到该片段末行之后」 |
| 设计文档改哪？ | issue 实现内容 4 | 07 §5.5.4 执行流 bullet 与 json5 示例注释 |
| 观测缺口（ConfigError 丢 detail）修不修？ | issue 实现内容 6 | 不修，不在本方案内扩大修改面 |
| Agent Note 放哪？ | [.agents/notes/README.md](../../../.agents/notes/README.md) 惯例 | `.agents/notes/implemented/bug-fix/2026-11-25-edit-insert-anchor-multiline` 三件套 |
| flow issue 怎么回填？ | [.agents/flow/README.md](../../../.agents/flow/README.md) 状态机 | `status: ready → in-progress`，`adr` 回填 note 路径，双语逐字节一致后 `pnpm record:i18n` |
| 生产计划原文能进仓库吗？ | issue 依赖与交付边界 | 不能；replay 测试只用合成安全副本（结构、行数与生产形状一致，不含生产原文） |

### Task 1: 失败回归（RED）

**Files:** Modify `apps/api/tests/test_edit_plan_applier.py`.

- [x] 新增测试：合成 4 行唯一块锚点的 `insert_after` 调用 `EditPlan.model_validate()`，断言当前实现抛 `target must be a single-line substring`（先红）。
- [x] 运行 `pnpm test:api -- tests/test_edit_plan_applier.py` 确认新用例红、既有用例绿。

### Task 2: validator 放宽 + 应用器按块定位（GREEN）

**Files:** Modify `apps/api/app/third_party_api/ai_agent/edits.py`.

- [x] 删除 `_validate_op_fields()` 中 `insert_after` 对 `\n` / `\r` 的拒绝；docstring 改为「insert_after 的 target 是文件内唯一出现的文本片段，可以跨行」。
- [x] 重写 `_insert_after_text()`：整段匹配唯一出现的 target；target 以换行（`\r\n`/`\n`/`\r`）结尾 → 插入点在该换行之后；否则插入点在匹配块末字符所在行的行终止符之后（EOF 无终止符 → 补 `\n`）；插入行沿用该行风格（`\r\n` 或 `\n`）。
- [x] `_apply_one()` 的 insert_after 分支删除单行拒绝，保留 `text.count(target)` 的 0 次 → skipped、>1 次 → ambiguous 分支；清除「not contained in one line」旧守卫。
- [x] 单行路径逐字节回归：`test_insert_after_last_line_without_newline`、四 op 精确内容用例、CRLF 用例全部保持通过。

### Task 3: prompt 与派生 schema 契约

**Files:** Modify `apps/api/app/service/evolution/patch_source.py`.

- [x] `_edit_prompt()` 的锚点行改为：「锚文本必须是文件内唯一出现的文本片段，可跨行；`insert_after` 把 content 插到该片段末行之后」。
- [x] 若 `test_ai_agent_claude_code.py` 断言 prompt 锚点文案，同步更新。

### Task 4: 设计文档同步

**Files:** Modify `plans/fullstack-design/07-backend-implementation.md`.

- [x] §5.5.4 json5 示例注释改为「锚文本：文件内必须存在且唯一，可以是跨行文本块」。
- [x] §5.5.4 执行流 bullet：「insert_after 行边界」改为「insert_after 块末行之后」，并在锚规则处写明「锚可以是单行或多行文本块」。
- [x] 全仓 grep `single-line substring` / `单行` 清理其它残留引用（docs/**、plans/**）。

### Task 5: 回归测试完善

**Files:** Modify `apps/api/tests/test_edit_plan_applier.py`.

- [x] 删除 `test_insert_after_rejects_a_multiline_anchor_at_model_construction` 及其参数行（`("insert_after", "line\nbreak", ...)` 断言 single-line 的行）。
- [x] 新增：4 行唯一块锚点通过校验，应用后 content 出现在块末行之后；文件其余字节不变。
- [x] 新增：单行 target（行中、行尾、EOF 无终止符）输出与旧实现逐字节一致（固定期望串断言）。
- [x] 新增：多行块 0 次 → `skipped_anchor_missing`；2 次 → `error` 且 message 含 `anchor is ambiguous`。
- [x] 新增：CRLF 文件中的多行块插入保持 `\r\n`。
- [x] 新增：`append` / `replace` / `delete` 既有语义不变的守卫断言（可复用既有用例，不必重复）。
- [x] 新增：生产计划形状 replay——8 条编辑、其中 1 条使用 4 行块锚点（合成安全副本），`EditPlan.model_validate()` 通过、`apply_edit_plan()` 只改目标文件、8 条报告全部 `applied`。

### Task 6: 文档、Note 与流程

**Files:** Create `.agents/notes/implemented/bug-fix/2026-11-25-edit-insert-anchor-multiline.{md,en.md,i18n.yaml}`; modify `.agents/flow/issues/bugfix-edit-insert-anchor-multiline.md` 与 `.en.md`.

- [x] Agent Note 三件套：Status: implemented；Problem / Decision / Alternatives considered / Consequences；记录「可见契约与 validator 契约不一致」的根因与「块末行之后插入」的决定。
- [x] flow issue 双语 yaml fence 逐字节一致：`status: ready → in-progress`、`adr: ../../notes/implemented/bug-fix/2026-11-25-edit-insert-anchor-multiline.md`。
- [x] `pnpm record:i18n -- .agents/notes/implemented/bug-fix/2026-11-25-edit-insert-anchor-multiline` 与 `pnpm record:i18n -- .agents/flow/issues/bugfix-edit-insert-anchor-multiline`。

### Task 7: 验证

- [x] `pnpm test:api -- tests/test_edit_plan_applier.py tests/test_ai_agent_claude_code.py`
- [x] `pnpm lint:api`、`pnpm typecheck:api`
- [x] `pnpm verify:flow`、`pnpm lint:docs`
- [x] 记录每条命令的实际结果；不提交截图或生产内容。
