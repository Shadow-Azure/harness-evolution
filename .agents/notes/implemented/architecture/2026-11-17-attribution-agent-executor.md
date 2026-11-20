# Agent Note: 归因 Agent 执行器契约接缝

Status: implemented

[English](2026-11-17-attribution-agent-executor.en.md) | 中文

## Problem

内网 LLM 与 Agent 当前不可访问，但把未来调用直接写进 Runner 会让 Skill 解析、输入组装、远程执行、输出校验、缓存和持久化耦合在一个事务路径中；本地与 CI 也无法证明替换真实引擎时仍遵守报告与证据契约。

## Decision

新增版本化 `AttributionExecutorRequest` 与 `AttributionExecutorResponse`，输入明确区分选定对象引入坐标和 Badcase 上报坐标，并只携带受界限约束的 Session 上下文、证据引用及不可变 Skill revision。`agent-skill-stub-v1` 通过同一协议执行确定性、无网络、无文件、无模型的规则桩，结构校验后投影到既有 `AttributionResult` 与 Probe Report V2。Run 启动按 effective Skill 的 executor type 选择引擎，Runner 按固化 key/revision/hash 读取正文而不读取当前 binding；真实 `agent` 在 adapter 缺席时拒绝启动。

## Alternatives considered

让 stub 直接复用 `rule-v1` 会掩盖 executor 输入输出和 Skill 正文没有真正贯通的问题，因此使用独立 engine key 和缓存身份。把完整原始 Trace 交给执行器会扩大隐私、载荷与缓存面，因此只传 m12-18 的裁剪上下文。把 Skill 正文复制进 Run 会增加敏感配置和迁移成本，不可变 revision 已提供可验证的历史寻址，因此只固化身份并按身份反查。

## Consequences

本地执行固定完整包的文件快照，停用或删除包后，排队中的运行仍可重放。输入同时携带选定对象、上报对象及原版本、空间可见 Session 树和脱敏轨迹。模型通过随包脚本提交分析，API 使用原始 case 和平台脚本重新生成并核对报告后入库。缺少原始轨迹时输入标明可用证据；脚本分类 `unknown` 映射到 V2 的证据不足。CLI 在逐次建立的文件系统沙箱中运行（macOS Seatbelt 或 Linux bubblewrap）。`HE_ATTRIBUTION_LLM` 选择模型提供方，`HE_ATTRIBUTION_TIMEOUT_SECONDS` 限制单 case 时长。

Badcase、Session 树、轨迹与上传的 Skill 都可能包含不可信指令。启用 Claude 后，逐 case 子进程可以读取本次输入和模型服务凭据，并可通过网络访问模型端点。Seatbelt 与 bubblewrap 限制文件访问；出站目的地由部署网络控制。对来源不受控的数据启用真实执行前，部署方应限制出站到获准模型端点，并为该服务签发可轮换、权限受限的独立凭据。
