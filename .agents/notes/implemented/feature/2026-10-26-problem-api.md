# Agent Note: 只读问题与归因 API

Status: implemented

[English](2026-10-26-problem-api.en.md) | 中文

## Problem

问题列表、深链详情和 Probe 反查需要同时读取规范化 Agent 树与外部只读问题三表。分开查询会拼出混合版本；直接按问题逐条查询又会造成 N+1，并容易让树与问题 API 各自实现不同的锚点规则。

## Decision

五个只读端点共享 `ProblemRepository` 的单一数据库会话快照：先读 Session、Agents、事件、问题和关联分析/Probe，再在内存中组合。`ProblemService` 复用 `BadCaseService` 的五态与漂移校验，并调用与 Session tree 相同的锚点解析器。

问题详情和归因接受可选 `sessionId` 作为深链归属证据；不一致返回 `409 BAD_CASE_SESSION_MISMATCH`。问题或 Probe 不存在使用独立稳定 404 码，缺归因行仍返回 `unanalyzed` 占位。主 Agent 上报者的返回 `agentId` 为 null，未知非主观测者保留外部 id 并把锚点安全降级到 main。

## Alternatives considered

- 每个问题单独查询分析和 Probe：拒绝，会产生 N+1，并破坏响应内的一致性。
- 前端自行比较 Session 归属：拒绝，跨会话语义必须由服务端权威判定。
- 缺归因时返回 404：拒绝，未分析是正常业务状态，不是资源缺失。

## Consequences

问题读接口保持只读且彼此一致；错误详情页面仍由后续 issue 实现。新增问题或锚点字段时必须同时更新共享 schema、OpenAPI 与树/问题两条读路径，避免两套语义漂移。
