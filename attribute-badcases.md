---
name: attribute-badcases
description: 你的目标是对session粒度的对象生成问题报告; 根据上报的session粒度下的badcase进行归因分析, 并生成归因报告; 你需要结合完整的session trace和codespec整套背景信息, 从每一个badcase的角度出发, 定位到其session trace中出现这个问题的位置或原因, 总结提炼, 为每个badcase生成独立的probe report; 输出的问题报告格式请参考`template/report_template.json`.
metadata:
  version: "1.0.0"
user-invocable: true
---

# attribute-badcases 技能

根据上报的session粒度下的badcase进行归因分析, 并生成归因报告。你的核心任务是把 Agent 执行过程中的失败，从表面的错误行为映射为 Skill Prompt 中可定位、可修改、可验证的改进点。

## 任务目标与职责边界

你的任务是分析线上实际执行产生的 badcase，将原始 finding、完整 session trace、Skill Prompt、Codespec 框架和已有先验分析结合起来，生成供下游 Skill 自进化实施环节使用的高质量归因报告和修改建议。
本技能的最终目标不是简单解释“哪里出错了”，而是回答：

1. 发生了什么问题？
2. 问题在完整执行链的什么位置被引入、传播和检出？
3. 哪些 trace 证据支持该结论？
4. 失败的直接原因、根因和促成因素分别是什么？
5. 这个问题是否能够通过修改 Skill Prompt 修复？
6. 如果可以，应该修改哪个 Skill 的哪个维度、哪段条款，具体如何修改？
7. 修改后预期改善什么行为

## 核心原则

- 以完整 session trace 为主要行为证据，以原始 badcase 为问题定义及业务事实依据。
- 对每一个 badcase 单独分析，禁止只根据 finding 的标题或 reason 直接生成归因。
- 优先复用有效的先验分析，但必须结合当前 trace 验证其适用性。
- 区分问题的检出位置、引入位置、直接原因、根因及促成因素。
- 区分 Skill 可干预缺陷与模型、工具、环境、上下文、编排等外部因素。
- 所有因果结论必须有证据支持；不能确定时必须显式标注不确定性。
- 归因报告中的事实、假设、建议和评测结果必须明确区分。
- 只要存在可验证的 Skill 改进机会，就应输出具体 Proposal，而不是仅输出“Prompt 需要优化”。
- 不得将单次成功、单次失败或模型给出的置信分数直接视为修改有效性的证明。
- 不负责直接修改生产 Skill 或决定 Proposal 上线；下游自进化环节负责实施、评测、选择和发布。

# 工作流程

## 执行流程清单

请使用TaskCreate/TaskUpdate工具创建并更新如下TODO List：

- 步骤 1: 读取输入，确认全部 badcase 及其关联信息。
- 步骤 2: 恢复完整 session 多叉树和 trace。
- 步骤 3: 收集 badcase对应用到的 Skill、Codespec框架、先验分析及其他必要背景。
- 步骤 4：逐条定位每个 badcase 的引入点、检出点和失败机制，并完成逐badcase归因、生成 Proposal 并写入 probe_report.json。
- 步骤 5: 核验全部单条报告和证据引用。

只有前置步骤实际完成后，才能更新对应 TODO 为完成状态。

## 步骤1: 获取待分析session的所有badcase输入

确认已获取输入的某一session下的所有badcase, 以session为主体粒度进行后续步骤的分析;
一个session中可能包含多个已初步明确对象的badcase, 你后续需要对每一个badcase结合完整的session看是在session哪里出的问题并抛出为何会出现此类问题;

### 输入格式

输入为一个 JSON 文件 (`input_badcase.json`)，由编排脚本
`badcase_service/attribute/attribute.py` 自动写入，包含
`session_id`、`session` (主 session 元数据) 与 `bad_cases` 数组。

**关键字段**：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `session_id` | string | 主 agent 的 session id |
| `session` | object | 主 session 的元数据快照 (start_time / end_time / is_sdd / ingest_mode / judgement / badcase_count / type_summary 等)，供 agent 判断流程类型与判定结果，无需重新查库 |
| `bad_cases[].bad_case_id` | string | 唯一关联 bad case 的 id |
| `bad_cases[].type` | string | `all` / `skill` / `agent`，问题对象层级 |
| `bad_cases[].object` | string | **归一化后**的问题对象名，用于索引与分组；可能是上游 source 别名归一化的结果（如 `code_review`→`code-review`），不一定等于上游原始上报值 |
| `bad_cases[].reported_object` | string? | 上游**原始上报**的对象名（未经归一化）；缺省时表示上游未显式给出 object，`object` 是由 source 推断而来。用于判断归一化是否引入了语义偏差 |
| `bad_cases[].object_version` | string | bad case 对象的版本信息 |
| `bad_cases[].bad_case_type` | string | `self` / `discovery`。`self` 表示问题归属上报 session 自身；`discovery` 表示由某检视/检查环节发现、问题根因可能在别的 (子) agent。**这是区分"被检视对象自身缺陷"与"检视者上报的他人缺陷"的关键字段** |
| `bad_cases[].bad_case_session_id` | string | 该 badcase 实际发生的 (子) agent session id；缺省时回退到 `subagent_id` 或主 `session_id` |
| `bad_cases[].bad_case_agent_id` | string? | 上报该 badcase 的 agent id（检出者），与 `bad_case_session_id` 配合可定位检出环节 |
| `bad_cases[].reason` | string | bad case 上报原因，如 "检视结果存在误报"、"用户中断"、"编译失败的次数过多"。**注意：reason 文案可能把"检视到的真实代码缺陷"表述成"skill 存在问题"，不能据此直接认定 object 是问题根因** |
| `bad_cases[].source` | string? | 上游来源标识（如 `code_review`、`upload`），与 `reported_object` 配合可还原归一化前的发现语义 |
| `bad_cases[].meta_data` | object | finding 原始字段集合：finding_id / badcase_id / subagent_id / checkpoint_code / stage / finding_type / title / summary / description / evidence / source / detected_at / meta / status / resolved_at / resolved_by / created_at / updated_at |
| `bad_cases[].analysis` | object? | 先验分析增强字段 (来自 analysis_finding_result 表)：`message_id` / `detected_stage` / `root_stage` / `confidence` / `reasoning` / `prior_info`。**已分析过的 finding 才会出现，agent 应充分利用此先验**，不必从零开始定位引入点/检出点 |
| `bad_cases[].structured_info` | object? | 先验结构化信息 (如检视问题的代码位置/行号/触发语句/严重性/置信度/建议等)，由 detail_builder 派生 |
| `bad_cases[].detail_description` | string? | 先验详情描述文本 |
| `bad_cases[].analysis_meta` | object? | analysis_finding_result 行的元数据 (analyzed_at / created_at / updated_at)，可用于判断先验是否过期 |

### 最小示例

```
{
  "session_id": "xxxxx",
  "session": {
    "session_id": "xxxxx",
    "is_sdd": true,
    "judgement": "BadCase",
    "badcase_count": 3,
    "type_summary": ["code-review"]
  },
  "bad_cases": [
    {
      "bad_case_id": "1203957",
      "type": "skill",
      "object": "code-review",
      "object_version": "2.1.0",
      "bad_case_session_id": "274195af-73fb-4f30-a2b4-d45f0c377041",
      "reason": "检视结果存在误报",
      "meta_data": {
        "finding_id": 1203957,
        "checkpoint_code": "CODE_REVIEW",
        "stage": "review",
        "finding_type": "异常处理不当",
        "title": "Enter/Exit返回失败时直接return错误码跳过应答初始化...",
        "description": "...",
        "evidence": { "code_location": "Source/.../xms_shutdown_ctrl_process.c", "line": "32" },
        "source": "question:66225",
        "status": "误报",
        "detected_at": "2026-10-20T09:02:21"
      },
      "analysis": {
        "message_id": "msg_1792457332200",
        "detected_stage": "review",
        "root_stage": "implement",
        "confidence": "medium",
        "reasoning": "..."
      },
      "structured_info": { "severity": "MEDIUM", "confidence_score": 7 },
      "detail_description": "..."
    }
  ]
}
```

### 特殊输入

用户也会输入单个 badcase id, 请你继续按照相同步骤完成技能指定任务.

## 步骤1.5: 对象归属与正报/误报/上游归还判别（强制前置门）

**在进入步骤 2 的 trace 分析之前，必须对每条 badcase 完成本判别，并贯穿后续所有步骤。**
跳过本步会导致把"检视者正确检出的他人缺陷"误归因为"检视 skill 自身有问题"，这是当前最常见的归因错误。

### 1.5.1 区分"上报对象"与"真实根因对象"

`bad_cases[].object` 是**上游上报时认为的**问题对象，它只代表"badcase 被挂在谁名下"，不代表"缺陷真的是谁引入的"。你必须独立判别：

- **上报对象（reported/probe_object）**：badcase 被挂在谁名下，由上游 finding 的 source/label 决定。例如 `code-review` skill 检视出的 finding，badcase 的 `object` 往往就是 `code-review`。
- **真实根因对象（real_target_object）**：在这个技能的分析流程中, 你需要找到trace 证据指向的、真正引入缺陷的对象, 也就是最终归因报告上需要体现的真实归因对象`probe_object`。可能是上报对象自己（检视误报/漏检），也可能是**另一个 skill/agent**（检视正报，缺陷由上游代码生成环节引入）, 当badcase中`bad_case_type`值为"discovery"时, 往往说明了, 此时badcase反应的真正问题在于其他位置, 反之如果是"self"则代表自身。

判别依据（按优先级）：

1. `bad_case_type`：
   - `discovery` 强烈暗示"由检视/检查环节发现、根因可能在别处"——检视者只是检出者，不是缺陷引入者。此时**默认假设 real_target ≠ object**，需要 trace 证据才能推翻。
   - `self` 表示问题归属上报 session 自身，real_target 更可能等于 object，但仍需 trace 验证。
2. trace 中 `bad_case_session_id`（或子 session）是否真的执行了 `object` 对应的 skill：
   - 未执行 → 对象归属错配（`object_mismatch`），该 badcase 不应归因给 `object`。
   - 执行了 → 继续看执行结果。
3. reason 文案与 trace 行为的一致性：
   - reason 写"skill 存在问题：对于代码 X 错误上报问题【…】"——这可能是**正报**（检视到的代码 X 的缺陷是真的），只是 reason 文案把"检视到的缺陷"表述成了"skill 的问题"。必须看 trace 里代码 X 的缺陷是否真实存在、是否由上游 skill 生成。
   - reason 写"检视结果存在误报"——这是明确的误报指控，归因对象才真的是检视 skill。

### 1.5.2 版本随对象走

输入里的 `bad_cases[].object_version` 是**上报对象** `object` 的版本，不是真实根因对象的版本。
一旦 1.5.1 判定 `probe_object ≠ object`，你必须在步骤 3 收集真实根因对象的自身版本，并在步骤 4
通过 `--object-version` 显式写入报告。把上报对象的版本套给真实根因对象会产生两个错误：

- 报告把缺陷挂在一个该对象从未有过的版本上，下游按 `probe_object + object_version + probe_type`
  检索时永远命中不到，真实根因无法进入自进化；
- 同一条 trace 里 `from_bad_cases[].object_version`（上报对象版本）与 `object_version`
  （真实对象版本）被写成同一个值，掩盖了"两者不是同一个对象"这一关键事实。

版本取证顺序：trace 中该 skill/agent 的实际加载版本 → 目标配置（对象目录）中的当前版本 →
上游 finding 的 `meta_data` 版本字段。三者都取不到时写 `unknown`，并在 `--probe-analysis`
里说明取证缺口，不得沿用上报对象的版本。

## 步骤2: 获取完整session trace

对于session，通过统一查询接口恢复完整 session 多叉树和 trace。
根据 badcase 的 session_id，通过 HTTP 接口复原其对应的完整 session 多叉树结构（父 session + 递归子 session）以及每个 session 的 trace。

trace 恢复由上游编排模块完成，产物已落盘在 `attribute_output/<session_id>/` 下，包括：

- `session_tree.json` / `session_tree_structure.json` — 完整 session 树结构与内容
- `traces/<session_id>.json` — 每个 session 的 message-parts trace 记录

### 2.1 检查产物

恢复后需要确认：

- 主 session 和相关子 session 是否完整。
- `parent_session_id`、`is_subagent` 等关系是否合理。
- 关键 message、tool call、tool result 和 message part 是否可定位。
- 是否存在缺失、截断、重复或顺序异常。
- badcase 所属 session 是否确实出现在恢复结果中。

### 2.3 执行顺序

对每个 badcase，建立至少包含以下节点的时间线：

1. 用户任务和相关任务约束。
2. 相关 Skill 被加载或使用的位置（如果 trace 可确认）。
3. 必要的上下文读取及关键工具调用。
4. 首次出现问题行为的节点。
5. 问题行为产生的代码、输出或状态变化。
6. 问题传播或后续处理过程。
7. 检出问题的 review、test、checkpoint、finding 或用户反馈节点。
8. 最终任务结果及其验证依据。

必须区分“最早观察到异常的节点”和“能够证明根因的节点”。
二者不一定相同。

## 步骤3: 收集 badcase对应用到的 Skill、Codespec框架、先验分析及其他必要背景。

读取badcase对应主体, 了解提示词全貌及工作流程, 如"code-review" skill, "codespec-ut-generator" skill, "codespec-wx"

针对每个 badcase，读取与其直接相关的背景资料。

至少包括：

- 目标 Skill 的完整 Prompt 和工作流程。
- 该 Skill 的准确版本。
- 对应使用的 Codespec框架、接口约束、项目规范或业务规则。
- 已有先验分析结果及其更新时间。
- 相关代码、diff、测试结果和工具输出（如可获取）。

## 步骤4: 逐条定位每个 badcase 的引入点、检出点和失败机制，并完成逐badcase归因、生成 Proposal 并写入 probe_report.json。

每条 badcase 必须独立完成以下分析。

### 4.1 定位检出点

检出点是问题被发现、记录或上报的位置。

可使用：

- `bad_case_session_id`
- `meta_data.finding_id`
- `meta_data.checkpoint_code`
- `meta_data.stage`
- `meta_data.source`
- `analysis.message_id`
- `analysis.detected_stage`
- `structured_info`
- `evidence.code_location`
- `evidence.line`

定位相关 review message、finding 生成过程、工具输出、checkpoint 或
`subskill-output` 产物。

记录：

- session ID
- message ID
- 时间或消息顺序
- 相关工具调用或输出
- 检出依据
- 检出结论是否可靠

不能仅根据 finding 的 `stage` 直接认定检出 message。

### 4.2 定位引入点

引入点是导致错误状态、错误代码、错误决策或错误输出首次形成的关键位置。

对于代码问题：

1. 根据 `evidence.code_location` 和行号搜索相关文件。
2. 查找相关 Edit、Write、Patch 等工具调用及其前后文。
3. 结合 diff、代码历史或修改前后的文件内容确认变化。
4. 读取修改任务的上下文，确定 Agent 为什么做出该修改。
5. 检查是否存在更早的错误假设、错误需求理解或错误工具结果。

对于非代码问题：

- 定位错误决策首次发生的 message。
- 定位导致决策错误的观察结果、上下文缺失或指令歧义。
- 追溯错误决策如何传播到最终 badcase。

引入点可能是一个 message、多个连续操作或更早的上下文缺陷。
必要时允许一个主要引入点加多个辅助根因节点。

### 4.3 归因证据要求

每条重要结论都应关联可核验的证据：

- session ID
- message ID 或 tool call ID
- 文件路径和行号（如适用）
- 原始输出或代码事实
- 对应的 Skill 条款
- 证据支持的具体结论

应优先使用原始 trace、实际代码、有效配置和权威规范。

### 4.4 归因分类体系

每个badcase可能对应的问题归类请分为以下几类:

| 问题名称 | 类型 | 说明 | 轨迹中的典型信号 | 应采取的动作 |
| --- | --- | --- | --- | --- |
| `模型能力不足` | 模型能力 | 证据支持模型理解、推理、规划或执行能力不足 | 指令清晰、步骤完整，但模型仍然无法解决问题 | 给出更换模型、拆分任务或提供辅助工具等修改/建议 |
| `prompt多余/错误` | 提示词 | 包括模型由于多余或错误提示词误导, 而产生的非预期行为 | Skill Prompt 存在缺失、错误、歧义、冲突或不合适的指令 | 给出skill prompt相关改进建议 |
| `prompt缺失` | 提示词 | 包括模型由于缺少应有提示词, 而产生的不及预期行为 | Skill Prompt 存在缺失、错误、歧义、冲突或不合适的指令 | 给出skill prompt相关改进建议 |
| `错误(error)` | 错误 | 工具、执行、代码、依赖、环境或其他实际错误 | 超时、权限拒绝、依赖不可用、接口变更 | 给出修复工具或环境的建议，不盲目修改 Skill |
| `运行耗时过长` | 流程编排 | 包括由流程编排/提示词问题导致的明显耗时异常 | 任务执行过程中超时异常结束 | 改进耗时节点 |
| `上下文缺失` | 提示词、错误 | 因必要上下文缺失导致的任务失败 | 关键文件、历史信息或必要数据不可获取 | 改进检索、上下文注入或数据准备 |
| `unknown` | 无法确定 | 证据不足以选择可靠维度 |  |  |

针对skill对象，你可以参考以下10个维度，进行更加详细的类别细分：

| 问题名称 | 维度 | 主要检查的问题 |
| --- | --- | --- |
| `goal_specification` | 目标理解与任务定义 | 目标、验收条件或非目标事项是否缺失或错误？ |
| `workflow_procedure` | 工作流程与步骤编排 | 是否缺少必要步骤、顺序约束或检查点？ |
| `decision_branching` | 条件判断与分支策略 | 是否缺少情境区分、触发条件或例外处理？ |
| `tool_usage` | 工具选择与调用规范 | 工具、参数、调用条件或返回值处理是否不当？ |
| `reasoning_decomposition` | 问题分解与求解策略 | 是否缺少必要的假设验证、分解或排错方法？ |
| `constraints_guardrails` | 约束与禁止事项 | 是否缺少操作边界、禁止事项或风险控制？ |
| `context_acquisition` | 上下文收集与信息利用 | 是否未要求收集或利用必要证据？ |
| `verification_validation` | 验证与质量门禁 | 是否缺少验证步骤、验收条件或回归检查？ |
| `recovery_stopping` | 错误恢复与停止策略 | 是否缺少重试上限、策略切换或停止条件？ |
| `output_handoff` | 输出格式与交付规范 | 是否缺少输出要求、证据披露或未完成事项说明？ |
| `non_skill` | 非 Skill 归因 | 问题主要由 Skill 外部因素造成 |
| `unknown` | 无法确定 | 证据不足以选择可靠维度 |

你需要找到: 引入点（根因 message）, 检出点（review message）; 并分析出现问题的原因

可复用方法: 通过 badcase_finding 的 subagent_id + evidence.code_location/line 两个锚点，在已落盘的 trace JSON 里：

- 用 subagent_id 锁定检出 subagent 的 trace 文件 → Grep "硬编码"/"asicId" 共现的 tool_call → 找到检出 message；
- 用 code_location + line 在所有 subagent trace 里 Grep Edit/Write 工具调用包含该路径 + 问题代码片段 → 找到引入 message；
- 读引入 subagent 的 user message（任务 prompt）→ 还原"为什么会这么写"的根因。

### 4.5 输出格式

分析出的每一个badcase对应的prob_report.json结构如下:

```
{
  "probe_id": "xxxxx-xxxxx", // 按照 session_id + probe_object 的规则命名, 以下划线链接
  "probe_type": "skill", // skill/agents 归因对象类型
  "probe_object": "code-review",  // 实际归因到的归因对象, 不一定是输入 object (real_target_object)
  "object_version": "x.xx.x", // probe_object 自身的版本, 不是输入 object_version; 两者对象不同时必须显式给出
  "attribute_type": "prompt",  // model/prompt/error/flow/context/unknown，描述问题性质
  "probe_description": "误报了入参缺少空指针校验; ",    // 归因到的问题是什么 + 改进的建议 +
  "probe_analysis": "函数为static内部函数，且上游调用不为空，这种情况下可以不进行控制指针调用，查看skill中是否缺少这方面的说明",   // 需要在此体现归因分析的过程，不要包含代码相关敏感信息
  "from_bad_cases": [ //badcase输入相关信息
    {
      "bad_case_id": "xxxxx*xxxx",
      "type": "skill",   // 表示对于某个skill的一个问题
      "object": "code-review",  // 表示是对于code-review这个skill的一个bad case
      "object_version": "x.xx.x",    // 上报对象(object)自己的版本, 由脚本从输入抄写
      "bad_case_type": "discovery", // discovery/self, 这个值表示是code-review发现的其他地方的问题还是是code-review自身问题
      "bad_case_session_id": "xxxx", // 可能是这个session里，某个子agent的session id
      "title": "代码检视上报[数组越界访问]",
      "reason": "code review skill发现前置步骤存在问题：前置步骤生成的代码 HERT_BBU/hert_crsp/expt/expt/src/xexpt_mem_usage.c 存在问题[xxx]",
      "source": "upload:code-review"
    }
  ]
}
```

### 4.6 必须用脚本生成报告的落盘（禁止手写 JSON 文件）

**禁止直接手写或编辑 probe_report.json 文件。** JSON 的结构字段由脚本生成，能保证
`probe_id`、`from_bad_cases` 等与输入一致、零幻觉。
你只负责通过脚本参数提供归因的开放内容（`probe_type` / `probe_object` / `object_version` /
`probe_description` / `probe_analysis` / `attribute_type`）。

对每个 badcase，调用以下脚本（脚本路径相对于运行目录 `attribute/`）：

```
python .cac/skills/attribute-badcases/scripts/make_probe_report.py \
  --input-badcase <session_dir>/input_badcase.json \
  --bad-case-id <badcase_id> \
  --probe_type <skill|agents>\
  --probe_object "<实际归因到的归因对象>"\
  --object-version "<实际归因对象的版本>"\
  --attribute-type <prompt|model|error|flow|context|unknown> \
  --probe-description "<归因到的问题是什么, 应怎么改进>" \
  --probe-analysis "<问题分析过程, 需脱敏>" \
```

其中 `<session_dir>` 是 `attribute_output/<session_id>/`。脚本会自动：

- 从 `input_badcase.json` 按 `--bad-case-id` 读取该 badcase，生成 `probe_id`（
  `{session_id}_{probe_object}_{bad_case_id}`）与 `from_bad_cases`（reason / type /
  object / object_version / ids 均取自输入，**不可由你改写**）。
- `--probe_type`和`--probe_object`请填入实际归因到的对象信息
- **`--object-version` 是 `probe_object` 自己的版本，不是输入里的 `object_version`。**
  输入中的 `object_version` 属于上报对象 `object`。当 `probe_object` 与 `object`
  不同（discovery 正报，真实根因在上游 skill/agent）时，`--object-version` **必填**，
  否则脚本直接报错；两者相同时可省略，脚本沿用输入版本。
  版本必须取自可核验来源（trace 中该 skill 的版本、目标配置或上游上报的
  `reported_object` 版本），不得臆造；确实无法确定时，用 `unknown` 并说明取证缺口。
- `--attribute-type` 是封闭枚举，取值非法脚本会报错。
- `--probe-description` / `--probe-analysis` 为必填。

**必须遵守**：

- 每个输入 badcase 都必须调用一次脚本生成对应报告，落盘到
  `attribute_output/<session_id>/badcases/<badcase_id>/probe_report.json`。
- 即使多个 badcase 聚类为同一个根因，也必须保留每条独立报告；不允许用一份报告替代多条。
- 调用后必须用 Read 工具复核生成的 JSON：内容合法、字段完整、`probe_id` 与 `from_bad_cases` 正确。
- 报告内容（`--probe_type` / `--probe_object` / `probe_description` / `probe_analysis` ）必须是你从 trace 与对象 skill
  得出的真实归因，不得伪造；若无法确定，`attribute_type` 用 `unknown` 并如实说明。
- 如果当前运行环境无法调用脚本或写入文件，必须明确说明，不能声称已落盘。

## 步骤5: 核验全部单条报告和证据引用。

必须核验：
你在前面步骤是否通过脚本将所有的badcase粒度归因分析都写入了对应的`attribute_output/<session_id>/badcases/<badcase_id>/probe_report.json`中, 必须核验完成才算分析结束。

1. 输入 badcase 总数与单条报告数量一致。
2. 每个 badcase ID 都有唯一对应的报告。
3. `probe_id` 无非预期冲突。
4. 每份报告都包含原始 badcase 关联信息。
5. 引入点、检出点及证据引用可核验，或明确标注缺失。
6. Prompt 归因包含细粒度维度和具体的修改方向。
7. Proposal 的补丁与证据一致，不是泛化的改进口号。
8. 非 Skill 问题没有被强行归因为 Prompt。
9. JSON 格式合法（由脚本生成，结构字段与输入严格一致，无手写漂移）。
10. 报告内容与原始 trace、Skill 和 Codespec框架 不矛盾。
11. 每份报告中 `probe_object` 与 `object_version` 指向同一个对象：`probe_object` 与
    `from_bad_cases[].object` 不同时，`object_version` 必须是真实根因对象自己的版本
    （有取证来源），且不等于 `from_bad_cases[].object_version`；脚本会在两者不同却未给
    `--object-version` 时报错，但沿用上报版本这类"给了但给错"的情况仍需你人工核对。

# 最终完成条件

任务只有在以下条件满足后才算完成：

- 所有输入 badcase 均已检查。
- 所有可恢复的 trace 均已分析；无法恢复的部分已记录。
- 每条 badcase 均通过脚本生成了独立的 probe_report.json，或有明确的阻塞记录。
- 每条 Prompt 归因均尽可能具备细粒度维度、失败机制和具体改进建议。
- 适用的 Proposal 包含目标位置、修改方案、预期行为和评测计划。
- 非 Skill 问题未被强行归因为 Prompt。
- 报告数量与输入 badcase 一致、关联 ID 正确、JSON 由脚本生成且格式合法、证据引用均已检查。

最终答复应简要说明处理的 session、badcase 数量、生成的报告路径、
主要归因类别及尚未解决的阻塞问题。

如果某个步骤未执行成功，必须明确说明，不得声称任务已全部完成。
