# Agent Note: 归因 Golden 影子评测与晋级门禁

Status: implemented

[English](2026-11-18-attribution-golden-promotion-gate.en.md) | 中文

## Problem

归因输出会进入聚类、Proposal 和 Patch，仅验证 Probe Report JSON 合法无法发现错误对象结论、虚假 evidence、提示注入或上下文降级。新引擎或 Skill revision 若能直接成为空间默认，会把未经对照的行为扩散到正式归因链，且事后无法还原人工接受依据。

## Decision

仓库维护脱敏且版本化的 Golden Set，影子评测复用正式执行器输入、输出和 Probe Report V2 投影，但不调用 Runner，也不写 Run、Probe Report、候选、聚类或缓存。报告同时计算结论与分类准确率、evidence 有效率、引入/检测点命中率、schema、安全、失败、延迟和 Token 指标；确定性 evaluation hash 排除观测延迟。每次评测、接受、驳回和回滚写入独立 append-only 事件，revision 保存当前 `candidate/eligible/rejected` 状态。只有 `eligible` revision 可成为 Workspace 默认；target 绑定仍允许候选版本用于受控试验。管理员只能接受通过全部阈值的同一份持久化报告，回滚优先选择同 Skill 的上一 eligible revision，否则回到平台 `rule-v1`。

## Alternatives considered

没有把影子结果写入正式 Probe Report 并加标志位，因为任何共表路径都可能被缓存、聚类或下游查询误消费。没有只在 CI 保存一次性 JSON，因为运行环境中的人工接受与回滚需要可审计身份。没有禁止 target 绑定候选版本，因为对象级小范围试验是生成真实对照的必要入口；生产默认仍由质量状态硬门禁。

## Consequences

stub 可在不访问内网模型的情况下验证完整晋级结构，真实 Agent 接入后复用同一 Golden 输入和门槛。rule-v1 的现有平台默认被显式标为 eligible，但对照报告会保留其 evidence 与安全指标差距。Golden Set 变化会产生新 hash，旧评测不能冒充新基线；阈值、评测清单、人工理由和回滚目标均可追溯。
