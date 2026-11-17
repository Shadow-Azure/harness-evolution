# Agent Note: 归因 Agent 执行器契约接缝

Status: implemented

[English](2026-11-17-attribution-agent-executor.en.md) | 中文

## Problem

内网 LLM 与 Agent 当前不可访问，但把未来调用直接写进 Runner 会让 Skill 解析、输入组装、远程执行、输出校验、缓存和持久化耦合在一个事务路径中；本地与 CI 也无法证明替换真实引擎时仍遵守报告与证据契约。

## Decision

新增版本化 `AttributionExecutorRequest` 与 `AttributionExecutorResponse`，输入明确区分选定对象引入坐标和 Badcase 上报坐标，并只携带受界限约束的 Session 上下文、证据引用及不可变 Skill revision。`agent-skill-stub-v1` 通过同一协议执行确定性、无网络、无文件、无模型的规则桩，结构校验后投影到既有 `AttributionResult` 与 Probe Report V2。Run 启动按 effective Skill 的 executor type 选择引擎，Runner 按固化 key/revision/hash 读取正文而不读取当前 binding；真实 `agent` 在 adapter 缺席时拒绝启动。

## Alternatives considered

让 stub 直接复用 `rule-v1` 会掩盖 executor 输入输出和 Skill 正文没有真正贯通的问题，因此使用独立 engine key 和缓存身份。把完整原始 Trace 交给执行器会扩大隐私、载荷与缓存面，因此只传 m12-09 的裁剪上下文。把 Skill 正文复制进 Run 会增加敏感配置和迁移成本，不可变 revision 已提供可验证的历史寻址，因此只固化身份并按身份反查。

## Consequences

内网 adapter 可实现相同 executor 协议并注册 engine key，而不修改 Runner、repository 或报告写入；stub 报告固定带 `AGENT_EXECUTOR_STUB`，缺失完整上下文时另带 warning，不会被误认为真实归因质量。执行器当前无超时控制和模型配置指纹，接入远程 adapter 时必须在接缝外增加超时、重试、凭据注入及非 `none` 的模型配置指纹。
