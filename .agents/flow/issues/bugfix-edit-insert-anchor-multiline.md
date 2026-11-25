# edit 提交校验拒绝合法的多行 insert_after 锚点，导致 patch 阶段整轮失败

[English](bugfix-edit-insert-anchor-multiline.en.md) | 中文

```yaml flow
kind: issue
id: bugfix-57
milestone: bugfix
depends:
  - bugfix-46
priority: P2
status: in-progress
scope:
  - apps/api/app/third_party_api/ai_agent/edits.py
  - apps/api/app/service/evolution/patch_source.py
  - apps/api/tests/**
  - docs/**
  - plans/**
  - .agents/**
adr:
  - ../../notes/implemented/bug-fix/2026-11-25-edit-insert-anchor-multiline.md
github:
  number: 599
  url: https://github.com/Shadow-Azure/harness-evolution/issues/599
```

## 背景

2026-11-25 09:29:41（CST），生产 full run `01M885592456VVK5B68DSMRKTE`（workspace `01M7KJ05ENF9784GPBDV544VB0`，对象 `codespec-subagent-driven-development@openspec-cn-main-copy-ar-a7ec200-claude-core`）启动第 6/7 步「迭代优化」。前两轮候选都通过评测并被接纳，第 3/10 轮在补丁生成阶段直接失败：

```text
status=failed
error.stage=patch
error.message=claude-code edit submission failed validation
at=2026-11-25T09:52:38+08:00
```

- 生产页面：`http://8.149.232.63/workspaces/01M7KJ05ENF9784GPBDV544VB0/evolution/runs/01M885592456VVK5B68DSMRKTE`
- 失败时运行的 release：`/opt/harness/releases/d8c5d23f38c618e0aa80b33e84808567f528887a`（即 `d8c5d23f`，PR #591 的合并提交）。

### 问题描述

run 的持久事件（`GET /api/evolution/runs/{id}/events`）把失败收缩到一次 `agent.edit` 调用，且这次调用不是「没写文件」「文件解析不了」或「工具面没有 Write」，而是**提交的 JSON5 文档已经被解析成对象，但 Pydantic 校验拒绝了它**：

| seq | 事件 | 关键字段 |
|---|---|---|
| 20 | `ai_agent_call` `agent.edit` ok（第 2 轮） | `outcome=ok`、tokens>0 |
| 21–27 | 第 2 轮的 candidate / push / eval / apply | 候选被评测接纳 |
| 28 | `ai_agent_call` `agent.edit` **error**（第 3 轮） | `model=MiniMax-M3.1-Flash[1m]`、`latencyMs=200674`、`costUsd=1.482657`、`inputTokens=64634`、`outputTokens=36631`、`attempts=1`、`submissionRounds=1`、`submissionParsedBy=json5`、`submissionRepaired=false`、`submissionParseFailures=0`、`submissionValidationFailures=1`、`sessionId=null` |
| 29 | `run_failed`（candidate 阶段） | `type=ConfigError`、`detail` 只有同一句泛化 message |
| 30 | `run_failed`（step 阶段） | `detail` 只有 Python traceback，仍然没有字段级校验原因 |

由此可以先排除四类常见原因：

1. **不是解析失败**：`submissionParsedBy=json5`、`submissionParseFailures=0`、`submissionRepaired=false`，说明 JSON5 文档被正常读出并解析成对象。
2. **不是文件缺失或权限被拒**：`submissionRounds=1` 且校验确实跑到了 Pydantic；文件缺失会得到 `missing`，写入被拒会带 `permission denied:` 的 detail，两者都不是本路径。
3. **不是 edit 工具面回归**：文件已经写出来，说明 `Write` 可用；bugfix-46 / PR #566 修好的 `--tools`、`Edit(//<abs>)` 规则在本次调用里是生效的。
4. **不是最近 PR 整体改坏了 edit**：同一 release、同一个 run 的第 1、2 轮 `agent.edit` 都是 `ok` 并被接纳；失败只发生在第 3 轮。

补充一条同路径的处置边界：如果 JSON5 连解析都失败（strict JSON → JSON5 → json-repair 三级都不成立），`submission.collect()` 会返回 `invalid + parse_error`；edit 路径同样不重试，直接以 `retryable=False` 终止，只有 analyze 会带 `feedback_prompt()` 重试一次。因此对 edit 来说，解析失败与校验失败是同一个终态，区别只在 detail 内容。

真正的原因藏在提交文件里。该调用失败后，`.harness-evolution/edits.json5` 仍留在生产 workspace（20,628 字节，未被删除）。把它取回后用**该 release 自己的代码和 venv** 复现校验，得到确定的字段级错误：

```text
edits.6: Value error, target must be a single-line substring
```

`edits.6` 是 0-based 索引，即计划里的**第 7 条**编辑：`op=insert_after`，`file=skills/codespec-subagent-driven-development/SKILL.md`，`target` 是 `### 验收与回归` 模板的 4 行文本块（158 个字符），该文本块在 `SKILL.md` 中只出现 1 次。其余 7 条编辑、总编辑数 8（未超过 `EDIT_BUDGET=8`）、文件范围、每条 content 的行数（最多 28 行）、summary 与 rationale 都合法；**只有这一条因为 target 跨行被拒绝**。

### 根因分析过程

1. **确认失败类别**：从 `ai_agent_call` 的 `submission*` 计数确认「已解析、校验失败」，而不是 `missing` / 解析失败 / 权限拒绝；从 `outcome=error`、`attempts=1`、`sessionId=null` 确认这次调用没有第二轮反馈。
2. **定位代码路径**：`ClaudeCodeProvider.edit_workspace()`（`apps/api/app/third_party_api/ai_agent/claude_code.py:403-476`）只调用一次 `self._submission.collect(prep, EditPlan.model_validate)`（:442）；只要 outcome 不是 ok，就以 `retryable=False` 抛 `claude-code edit submission failed validation`（:456-464），不会像 analyze 那样调用 `feedback_prompt()` 重试（对照 :266-322）。
3. **读生产残留提交**：从 workspace 取回 `.harness-evolution/edits.json5`；用 `json5` 解析得到 `{summary, edits}`，共 8 条编辑，全部落在 `skills/codespec-subagent-driven-development/SKILL.md`，所有 target 在 `SKILL.md` 中的出现次数都是 1，content 最多 28 行，均在 `EDIT_BUDGET=8` 与 `MAX_CONTENT_LINES=400` 之内。
4. **用发布代码复现**：在 release `d8c5d23f` 的 `api/` 下，用 `/opt/harness/shared/venv` 直接执行 `EditPlan.model_validate()`；结果稳定为 `edits.6: Value error, target must be a single-line substring`。这说明失败与模型 prose、stderr、网络、CLI 版本都无关，是 validator 对一个多行 `insert_after` target 的确定性拒绝。
5. **核对契约来源**：`EditOp._validate_op_fields()`（`edits.py:158-179`）在 `insert_after` 分支显式拒绝含 `\n` / `\r` 的 target（:171-172），`_apply_one()`（:482-527）里还有同一检查（:503）；但同一份 `EditOp` 的 docstring（:157-164）写的是「the retry prompt gets a field-level message」，而 edit 路径根本没有 retry prompt。设计文档 07 §5.5.4 与 flow issue bugfix-20（#494）的契约只要求「锚文本存在且唯一」，没有「单行」这一条；模型拿到的 `_edit_prompt()`（`apps/api/app/service/evolution/patch_source.py:511-558`）也只说「file 必须落在允许范围、锚文本必须存在且唯一」，派生的 JSON Schema 无法表达「target 不能有换行」这种条件约束。也就是说，**模型遵循了它被告知的契约（唯一锚点），validator 却执行了一条未公开、且与设计文档不一致的更严格规则**。
6. **核对「是否最近 PR 引入」**：
   - 失败 release `d8c5d23f` 是 PR #591（`fix(evolution): cluster by attribution conclusions`）的合并提交；该 diff 涉及聚类 / prepare / stages 与测试、文档，没有改 `edits.py`、`claude_code.py` 或 `patch_source.py`。
   - 最近一次改 edit 通道的是 PR #572（`64fffe72`，2026-11-24），它只改 `claude_code.py` 及其配套测试/文档（无头 argv / 工具面 / 失败证据），没有改 `edits.py` 或 edit prompt；而且它已在 `d8c5d23f` 里，正是它让 edit 能真正写出提交文件。
   - 「insert_after target 必须单行」是 PR #494（`d1accc70`，2026-11-23）加的，早于 #572 与 #591；此后所有 release 都带这条规则。严格说，如果「最近」指 11-23 的 #494，那么这条规则确实来自一次较近的合入；但它是**规则来源**，不是最近一次 edit 修复或失败 release 的回归。
   - #591 改变了送进 edit prompt 的聚类文案（问题簇从 bad case 标题改成归因结论），这次第 3 轮的簇正好指向「缺少阻断式验证门禁与回归失败分级证据」，可能会影响模型选择的具体编辑形态；但 #591 没有改 `edits.py` 的校验规则，无法解释「多行 insert_after 必然被拒」这个结构性结果。
   - 同 release 的第 1、2 轮 edit 成功、第 3 轮失败，符合单次模型输出的差异，而不是部署级回归。
7. **解释为什么只看到泛化错误**：`AgentProviderError.detail` 本来包含 `validation failed: edits.6: ...`（`_submission_detail()`，`claude_code.py:1222-1228`），但 `GitCandidateService._handle_provider_failure()` 在 `retryable=False` 时用 `ConfigError(sanitize_message(str(error)))` 转交 `_fail_patch_generation()`（`git_candidate.py:760-775`），`str(error)` 只有 message，detail 被丢掉；所以 run 的 `error` 与 job 的 `error` 都只剩 `claude-code edit submission failed validation`，字段级原因只存在于已经写出的 `edits.json5` 与本次复现中。

### 结论

- **直接原因**：计划第 7 条 `insert_after` 的 target 是一个 4 行文本块；`EditOp` 的 `insert_after` 分支要求 target 必须是单行，`EditPlan.model_validate()` 因此抛出 `edits.6: Value error, target must be a single-line substring`，`edit_workspace()` 以 `retryable=False` 失败，patch 阶段没有候选，整个 run 失败。
- **根因**：`insert_after` 的锚点契约在「模型可见的契约」与「validator 实际执行的契约」之间不一致。模型看到的 prompt、派生 JSON Schema 和 07 §5.5.4 设计都只说「锚文本存在且唯一」；validator 却额外要求「单行」，且这条规则没有出现在 prompt 或 schema 里。计划里的 4 行块是唯一出现的合法文本块，模型还专门在 summary 里写了「所有 target 锚文本均经唯一性校验」，说明它按可见契约做了正确的事。edit 又是单次调用、校验失败不重试，这个隐藏约束就直接把整轮打死。
- **是否由最近合入的 PR 导致：不是最近一次部署或最近一次 edit 修复造成的回归，但单行规则确实来自 11-23 的 #494。** PR #591 没有改 edit 校验，只改了聚类文案，可能影响这次模型选择的具体编辑形态；PR #572 是让 edit 能提交的修复，不是失败原因；「单行」规则来自更早的 #494，而 #494 的注释假设「字段级错误会进入 retry prompt」，edit 却没有 retry。第 1、2 轮在同一 release 上成功，也排除了「最近改动把 edit 整体改坏」。
- **为什么前两轮成功、第三轮失败**：前两轮模型提交的 plans 没有多行 `insert_after`，validator 通过；第三轮模型用了一个自然、唯一、但跨行的块锚点，触发隐藏规则。这不是 seed 或部署差异，是模型每次输出不同导致的单点契约不匹配。
- **诊断缺口（不改变上述根因）**：字段级 `detail` 在 `ConfigError` 转换时被丢弃，run 页与 job 只显示泛化 message；本次是通过读取残留 `edits.json5` 并用发布代码复现才拿到 `edits.6`。这是可观测性缺口，不是本次失败的原因，本 issue 的推荐方案不把它作为修复前提。

## 目标

- 让 `insert_after` 的锚点契约与模型可见的契约一致：文件内**存在且唯一**的文本片段就是合法锚点，允许跨行；不再要求 target 必须是单行。
- 让应用器在匹配块的**末行之后**插入 content，保持确定性、唯一性、scope/content/budget 限制不变；单行 target 的输出必须与今天逐字节一致。
- 把 prompt、派生 schema 的说明、设计文档与测试同步到同一个契约，消除「规则只存在于 validator」的结构性缺口。
- 用这次的生产计划形状做回归：同样的 8 条编辑、同样的 4 行块锚点，`EditPlan.model_validate()` 必须通过，`apply_edit_plan()` 必须只改 `SKILL.md` 并产出逐条 `applied` 报告。
- 不改变 edit 的单次调用模型（不新增反馈重试）、不改工具面、不改 `EDIT_BUDGET` / `MAX_CONTENT_LINES` / 超时。

## 设计依据

- [07 §5.5.4 Edit 指令式 patch](../../../plans/fullstack-design/07-backend-implementation.md)：EditPlan 契约、`insert_after 行边界`、确定性应用与安全闸；该节的锚点规则只有「存在且唯一」。
- [07 §5.5.3 六层 JSON 可靠性](../../../plans/fullstack-design/07-backend-implementation.md)：Pydantic 是提交校验的单一事实源，schema 由模型派生；调用方 prompt 必须把 schema 表达不了的语义约束说清楚。
- [bugfix-20 / #494](https://github.com/Shadow-Azure/harness-evolution/issues/494)：EditPlan 应用器的原始契约与「锚存在且唯一」的验收标准。
- [bugfix-46 / #566](https://github.com/Shadow-Azure/harness-evolution/issues/566)：edit 通道在真实 CLI 上恢复提交能力的修复；本 issue 处理其恢复之后暴露的下一层提交契约问题。
- [06 §4 / 07 §5.5.3 的失败可观测性](../../../plans/fullstack-design/07-backend-implementation.md)：`AgentProviderError.detail` 是字段级诊断的承载字段；本次它被 `ConfigError` 转换丢弃，作为诊断缺口记录，不在本方案内扩大修改。

## 实现内容

**唯一推荐方案：把 `insert_after` 的锚点统一为「存在且唯一的文本块」，允许跨行，并把插入位置定义为匹配块末行之后；同步 prompt、应用器、测试与设计文档。**

1. **放宽模型校验**：删除 `EditOp._validate_op_fields()` 中 `insert_after` 对 `\n` / `\r` 的拒绝（`edits.py:171-172`），保留 target 非空、`append` 禁止 target、`delete` 禁止 content、content/scope/budget 等全部其它约束。`EditOp` 的 docstring 改为「insert_after 的 target 是文件内唯一出现的文本片段，可以跨行」。
2. **应用器按块定位**：`_apply_one()`（`edits.py:482-527`）与 `_insert_after_text()`（:467-480）不再用「某一行包含 target」来定位。改为：
   - 在文件全文里按整段文本匹配 target，并要求恰好出现一次（沿用 `_apply_one` 已有的 `text.count(target)` 与多义/缺失分支）；
   - 找到 target 最后一个字符所在的行；若 target 自身以换行结尾，则以该换行之后为插入点；
   - 把 content 的行按该行现有的换行风格（`\n` 或 `\r\n`）插到该行之后；
   - 单行 target 走同一路径时，输出必须与现有实现逐字节一致（现有 `test_insert_after_last_line_without_newline` 等用例必须保持通过）。
3. **把契约写进 prompt**：`_edit_prompt()`（`patch_source.py:511-558`）把「锚文本必须存在且唯一」补成「target 是文件内唯一出现的文本片段，可跨行；`insert_after` 把 content 插到该片段末行之后」。这是模型可见的正向契约，不再依赖它猜测「单行」。
4. **同步设计文档**：在 07 §5.5.4 的执行流 bullet 中把「锚存在且唯一」明确为「锚可以是单行或多行文本块；`insert_after` 插入到块末行之后」，并同步 `plans/` 里的对应说明。
5. **补回归测试**：删除/改写 `test_insert_after_rejects_a_multiline_anchor_at_model_construction`（`apps/api/tests/test_edit_plan_applier.py:377-380`），新增：
   - 4 行唯一块锚点通过模型校验，应用后在块末行后插入；
   - 单行锚点的输出与旧实现完全一致；
   - 多行块出现 0 次 → `skipped_anchor_missing`，出现 2 次 → `error`（多义）；
   - CRLF 文件中的多行块插入保持 `\r\n`；
   - `append` / `replace` / `delete` 的既有语义不变。
6. **不改观测与重试**：`feedback_prompt()` 与 `edit_workspace()` 的单次调用结构保持原样；`ConfigError` 转换丢弃 detail 的问题不在本方案内处理，避免把修复面扩大到 run 错误模型。

## 实施步骤

1. 先加一条失败回归：用合成 4 行块锚点的 `insert_after` 计划调用 `EditPlan.model_validate()`，确认当前实现报 `target must be a single-line substring`。
2. 删除 validator 的单行拒绝，按「整段唯一匹配 + 块末行之后插入」重写 `_insert_after_text()` 与 `_apply_one()` 的 insert_after 分支；保持单行路径逐字节不变。
3. 更新 `_edit_prompt()` 的锚点说明与 07 §5.5.4 / `plans/` 的设计文字。
4. 改/补单测，覆盖单行回归、多行块、CRLF、缺失与多义；运行 `pnpm test:api -- tests/test_edit_plan_applier.py` 与 `tests/test_ai_agent_claude_code.py`。
5. 用生产计划的安全副本（只保留 summary 结构、4 行块 target 与 content 行数，不写入生产原文）做一次 end-to-end replay：`EditPlan.model_validate()` 通过，`apply_edit_plan()` 只改 `SKILL.md`，8 条报告全部 `applied`。
6. 部署后新建一次 full run，在第 6 步第 3 轮验证 `agent.edit` 为 `ok`，run 继续 candidate / push / eval；实现 PR 在同一提交内新增 Agent Note 并回填本 issue 的 `adr`。

## 依赖与交付边界

- 依赖：bugfix-46（#566，edit 工具面已修复且已合入；本 issue 处理其后的提交契约）。
- 只改 `edits.py` 的 `EditOp` / `_apply_one` / `_insert_after_text`、`patch_source.py` 的 `_edit_prompt()`、对应测试、`docs/**`、`plans/**` 与 `.agents/**`。
- 不改 `claude_code.py` / `submission.py` 的工具面、权限规则、超时与重试；不改 `EDIT_BUDGET`、`MAX_CONTENT_LINES`、`allowed_paths`；不改聚类、归因、评测、前端。
- 不把生产计划原文、Session 内容、截图或凭据写入仓库；本 issue 与实现 PR 只引用有界诊断字符串与合成样例。

## 独立验证

```sh
pnpm test:api -- tests/test_edit_plan_applier.py
pnpm test:api -- tests/test_ai_agent_claude_code.py
pnpm lint:api
pnpm typecheck:api
pnpm verify:flow
```

- 合成 4 行块锚点的 `insert_after` 通过 `EditPlan.model_validate()`，应用报告为 `applied`，content 出现在块末行之后。
- 单行 `insert_after` 的既有断言全部保持逐字节一致；多行块 0 次出现 → `skipped_anchor_missing`，2 次出现 → `error`（`anchor is ambiguous`）。
- 生产计划形状 replay：8 条编辑全部 `applied`，只有 `skills/codespec-subagent-driven-development/SKILL.md` 发生变化；`edits.6` 不再报 `single-line substring`。
- 新生产 run 的第 3 轮 `agent.edit` 为 `outcome=ok`、tokens>0、`submissionValidationFailures=0`，run 进入 candidate/push/eval。

## 验收标准

- `insert_after` 接受文件内唯一出现的多行文本块；content 插入在该块最后一行之后，结果确定、可重放。
- 同一份生产 plan 形状不再触发 `target must be a single-line substring`；`edits.6` 校验通过。
- 单行 `insert_after` 行为与今天逐字节一致；锚缺失、锚多义、scope 越界、content 超限、budget 超限仍按原规则拒绝或跳过。
- prompt、派生 schema 说明、07 §5.5.4 与 validator 表达同一个锚点契约，不存在只在代码里的隐藏规则。
- 一次真实 full run 能完成此前失败的第 3 轮并进入 candidate / push / eval。
- 仓库不新增生产凭据、Session 内容或计划原文。

## 门禁与 CI

- `pnpm test:api`（至少 `tests/test_edit_plan_applier.py`、`tests/test_ai_agent_claude_code.py`）、`pnpm lint:api`、`pnpm typecheck:api`。
- `pnpm verify:flow`、`pnpm verify:flow-online`、`pnpm lint:docs`。
- CI lane：`api-static`、`unit-tests-api`、`docs-flow`、`flow-online`。
- 实现 PR 的标题与提交必须含本 issue 编号；同一 PR 新增 Agent Note 并回填 `adr`。

## 非目标

- 不为 edit 增加反馈重试，不改变 agent-edit 的单次调用与失败即终止语义。
- 不放宽锚点唯一性、文件 scope、content 行数或 8 条编辑预算；不允许用多行 target 绕过唯一性检查。
- 不改 `claude_code.py` 的 `--tools` / 权限规则 / `EDIT_TIMEOUT_SECONDS` / `EDIT_MAX_TURNS`。
- 不改 `submission.py` 的解析、schema 派生或 `feedback_prompt()` 契约；不改 analyze 路径。
- 不把 `ConfigError` detail 丢失的观测缺口并入本方案；它不影响本次根因与修复验收。
- 不改聚类、归因、评测网关、前端或部署流程。
