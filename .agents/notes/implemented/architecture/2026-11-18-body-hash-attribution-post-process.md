# Agent Note: 归因身份改为归一化 body hash 与后处理锚点

Status: implemented

[English](2026-11-18-body-hash-attribution-post-process.en.md) | 中文

## Problem

生产环境 2026-11-18 的 `systematic-debugging` 目标是 skill；轨迹里的 skill 事件只有 `definitionHash=8e54…` 和 `objectRevision=digest:3643…`，其中 revision 由运行时注入的 source path 与 body hash 组合而成。同样的 `sha256(normalized_body)` 文件匹配需求也适用于 agent（`AGENT.md`）与 knowledge（文档文件读）：它们应共用同一 body hash，而不是各自保留 source/raw-content 身份。该 path 是 `.../claude-plugins-official/superpowers/6.4.1/skills/systematic-debugging/SKILL.md` 一类插件 cache 路径，既不是稳定相对路径，也没有落进 `agent_events`；因此 target 侧无法从 `repoUrl/subDir/ref` 复算出同一个 revision。实际结果是 tag `v6.4.1` 关联 0 个 Session，4 个已同步 Session 全部 skipped，18 个待同步，归因无法开始。

同时，找不到上报对象的 bad case 以 `eventIndex=-1` 表示；当前设计把它退化为上报 Agent 的出生点（主 Agent 为 Session 开始），所以这些后处理上报的 case 永远落在目标对象之前，potential 为 0。`eventIndex=-1` 在现有文档里是“锚点缺失/异常”，不是“后处理”语义；两类数据被混在一起，既无法解释，也无法按后处理规则参与归因。

## Decision

- skill/agent/knowledge 的**文件匹配键**统一为 `sha256(normalize_definition_body(body))`：skill 取 `SKILL.md`，agent 取 `AGENT.md`，knowledge 取文件读文档内容。skill 的对象身份使用该 body hash；agent 的 `object_revision` 保留 `agentType + isBuiltIn + body hash` 作为诊断身份，但 target 匹配用 `definition_hash`；knowledge 文件读的 `document_revision`/`object_revision` 也使用归一化 body hash，Provider 原始 revision 仍是 `provider:`。`source_path` 只保留为诊断证据，不参与 revision、缓存键或匹配。显式 tag/版本仍是最高优先级的版本证据；只有没有 tag 时才使用 body hash（knowledge 的 `defaultRef` 是文档 revision）。
- 进化向导里选择 tag 的动作表示“选择目标版本”：skill/agent 由服务端读取该 tag 下 `repoUrl/subDir/SKILL.md`/`AGENT.md`，knowledge 由文档 revision/内容读取；统一按与 parser 相同的 `normalize_definition_body` 归一化并计算 sha256。解析出的 `targetRevision=digest:<bodyhash>` 用于 Session 关联与缓存键，tag 继续作为版本/显示与代码基线。内容读取失败必须返回稳定错误，不能静默回退到 `tag:` 匹配。knowledge 目标仍通过 API 配置/启动，向导暂不提供 knowledge 选择器。
- 目标内容必须与轨迹来自同一制品/版本，并经过同一 body 提取与归一化；skill/agent 的 tag→body hash、knowledge 的文档 revision→body hash 与已知轨迹 `definitionHash`/`documentRevision` 的一致性作为验收测试。owner 确认 target 应使用 `superpowers` `main`。eval trace 已收到：trace 的 skill body hash 是 `8e54…`；main 的 `SKILL.md` 整文件 hash 是 `a9a7…`，去掉 YAML frontmatter 后 body hash 正好是 `8e54…`；v6.4.1 的整文件 `9080…` 去掉 frontmatter 后是 `580c…`，与 trace `8e54…` 不一致；v6.4.1 与 main 的正文有 shell 示例差异，不能靠 frontmatter 补齐。生产 target 必须从 v6.4.1 切到 main；main 的 body 才能与 trace 对齐。target 内容解析对 skill/agent 文件使用 frontmatter-aware 的 `definition_file_hash`，knowledge 文件读仍对全文归一化；golden 测试证明 public main 的 resolver 与 parser 都得到 `digest:8e54…`。这是实现契约，不允许用名称或默认分支猜测。
- 找不到上报对象时，skill/agent 的锚点改为后处理锚点：`eventIndex=2147483647`（INT_MAX）、`anchorKind=post_process`、`triggeredAt=bad_case.created_at`。比较时 `post_process` 直接视为“对象之后”，不依赖 `created_at` 与对象进入点的时间先后；`created_at` 只作审计/显示，坐标兜底 INT_MAX。`-1` 只保留给“上报 Agent 本身无法解析”的 unknown。树/API 增加 `anchorKind`；候选行记录 `case_anchor_kind=post_process`，潜在行通过 `anchorSource=post_process` 暴露，使“为什么可归因”可审计。
- 兼容边界：parser version 从 5 递增到 6 并重放存量 claude-code 会话；旧 path+body revision 保留为历史，不再作为新 run 的身份；新 run 只写 body-only revision。旧缓存键不复用；需要时单独清理。知识库 UI 选择器、私有仓库凭据与 rule-v1 分类不在本决策范围。
- 本 Note 记录该决策与实现边界；parser、target 内容解析、matcher、契约/UI、迁移与测试已在同一 M13 交付中落地；后续修正以本 Note 为 owning decision。

## Alternatives considered

- **保留 path + body hash，只把 path 归一化成相对路径**：运行时 path 是插件 cache 路径，不是稳定的仓库相对路径；且当前没有把 path 落库，target 无法复算。要支持就得新增 path 归一化契约和持久化，仍然绑定插件缓存形状；比 body-only 更复杂。
- **只在 target 匹配时使用 body hash，保留 path+body 作为对象身份**：会同时存在两个身份，缓存键、归因行和诊断语义都要双写；短期可作为迁移兼容，但不应作为长期设计。本决策选择单一 body-only 身份。
- **agent 继续用 `agentType + isBuiltIn + body hash` 作为 target 匹配键**：类型/builtin 是诊断证据，不是文件匹配键；否则同一 body 的 agent 目标会因类型/内置标记不同而失配。target 匹配统一用 `definition_hash`。
- **knowledge 继续用原始内容 hash**：与 skill/agent 的 `sha256(normalized_body)` 不一致；文件读应统一用归一化 body hash，Provider 原始 revision 仍保留为 `provider:`。
- **继续把 tag 当作 revision**：tag 只说明版本名，不说明该版本的内容 hash；内容与轨迹不一致时无法发现，且当前例子已经证明 tag 文件 hash 与 trace 不同。tag 应作为内容选择入口，而不是最终 revision。
- **只把 `eventIndex` 改成 MAX**：比较先看 `triggered_at`，主 Agent 的出生点有 `session_started_at`，MAX 只影响坐标兜底；matcher 还会重新解析锚点，不读展示锚点。必须同时定义后处理触发时间（`created_at`）与 `anchorKind`，否则 MAX 不生效。
- **继续用 -1/出生点兜底**：会把后处理 case 当成“对象之前”，让本可解释的后处理数据永远不进入 potential；也无法区分“找不到对象”和“上报 Agent 无法解析”。显式后处理语义更可解释，但也需要策略确认，避免把无关 case 过归因。

## Consequences

- 需要 parser version bump 与存量重放（skill/agent/knowledge）；旧 path+body revision、缓存键与归因行保留历史语义，新 run 使用归一化 body hash。数据库列长度（96）足够容纳 71 字符的 `digest:<sha256>`。
- target 侧新增内容读取/归一化/缓存与超时边界：skill `SKILL.md`、agent `AGENT.md`/`agent.md`、knowledge 文档内容；当前 target 配置是无凭据 HTTPS/SSH，私有仓库内容读取不在本轮范围。读取失败要有稳定错误码，不能回退到 tag 猜测。
- knowledge 的 `KnowledgeContentSource` 是注入缝；生产未绑定文档 Provider 时，裸 revision（非 `digest:`/`provider:`）只能返回 `TARGET_CONTENT_UNRESOLVED`，`digest:`/`provider:` 可直接启动。
- `post_process` 在潜在匹配中直接视为“对象之后”，不再依赖 `created_at` 与目标进入点的时间先后；`created_at` 只作审计/显示时间，树/接口坐标仍用 INT_MAX 兜底。这样避免 created_at 早于对象进入点时后处理 case 仍为 0 潜在；仍需要 `anchorSource` 与潜在策略审计，必要时用开关控制。
- 树/API 增加 `anchorKind`，前端要把 MAX 显示为“后处理”而不是巨大数字；`BadCaseAnchor.event_index` 的 `ge=-1` 不拒绝 INT_MAX，但契约/测试要覆盖该哨兵。
- 当前生产例子的 tag 文件 hash 与 trace body hash 不一致，必须先确定真实来源/版本和 body 提取；否则即使改完 body-only，target 仍可能 0 关联。设计文档与验收测试必须把这个前置写死，不能用名称或默认分支猜测。
