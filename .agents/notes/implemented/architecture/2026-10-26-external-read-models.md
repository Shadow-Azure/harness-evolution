# Agent Note: 外部问题只读读模型

Status: implemented

[English](2026-10-26-external-read-models.en.md) | 中文

## Problem

`bad_cases`、`bad_case_analysis`、`probe_reports` 由外部系统写入。若 API 直接读取表或逐条拼装归因，外部字段漂移、非法 probe 链接和 N+1 查询会把上游问题扩散为页面故障，并且容易误把本服务变成外部表的写入方。

## Decision

外部三表由 `db/crud/bad_cases.py` 在单一读取会话中批量 SELECT，service 只负责五态归并。应用启动迁移只维护本服务内表，外部三表仅由显式开发 fixture bootstrap 或外部所有者创建。`analyzed_issue` 必须有同会话的 probe，`analyzed_nonissue` 与 `unanalyzed` 不得挂 probe；任何不一致降级为 `unanalyzed` 并产生稳定 code 的脱敏 warning。probe 反查来源只接受 `analyzed_issue` 且 case/probe 同会话的有效链接。`analysis_result` 按状态校验 issue 的 `summary` 与 non-issue 的 `reason/reasoning[]`，形状漂移时保留状态但清空快照。身份字段缺失跳过该行并以 lookup 诊断返回，非身份字段异常保留可读占位；数据库时间在出站边界统一为 Asia/Shanghai。五态是查询期派生，不增加数据库枚举或派生列。

## Alternatives considered

在 `sessions` service 内继续拼装会混淆会话树和外部问题边界；为五态增加派生列会复制外部事实；遇到漂移直接返回 500 会让单个坏行中断整页。开发 fixture 需要自包含测试和演示，因此通过显式 bootstrap 开关创建外部表；应用运行时迁移和 repository 都不写这些表。

## Consequences

m4-02 必须通过这个 service 消费问题并补充 HTTP 错误映射。外部字段继续漂移时页面会降级而不是崩溃，但 warning 需要可观测；m4-01 不提供问题 API 或前端页面。生产部署必须先由外部表所有者创建 schema，再启动 API。
