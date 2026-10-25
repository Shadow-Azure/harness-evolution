# Agent Note: 上游轨迹查询边界

Status: implemented

[English](2026-10-26-upstream-trace-contract.en.md) | 中文

## Problem

上游轨迹接口尚未实现，但本服务必须在不接真实服务的情况下固定版本、分页、重试、逐会话失败隔离和原始 payload 写入语义。

## Decision

上游契约作为独立 outbound contract 放在 `third_party_api/trajectory/`，由严格、冻结的 Pydantic 模型生成 JSON Schema 与 fixture，不塞入 FastAPI inbound OpenAPI。

`HttpTrajectorySource` 使用注入的 `httpx.AsyncClient` 与 mock transport 测试；`HE_UPSTREAM_API_MAJOR` 只允许 `1` 并在配置装载时拒绝其他主版本，响应头仍逐次校验。429、5xx、超时和传输故障最多补试三次，普通 4xx 与版本错误不重试。注入 source 的 HTTP 资源由 FastAPI lifespan 在关闭阶段释放。

管理员 pull job 先把成功包转换为同一 `trajectory_payloads` 表的原始 JSONL 行，再由共享 root 重放管线处理；逐会话失败只进入脱敏 sync errors，不丢弃其他成功项。

运行时模型只接受 canonical camelCase aliases 与真实布尔值，不把 snake_case 或字符串布尔当成第二套 wire contract。导出的 JSON Schema 在 `transcripts` 数组上表达主 transcript 恰好一个，并要求主 Agent 无 id、子 Agent 有 id；子 id 不得复用 root id 通过 Ajv `$data` 引用表达，元数据时间使用 RFC 3339 date-time 与有序区间扩展，跨 transcript 的唯一性仍由运行时校验保证。上游来源统一记为 `http_api`。主版本不兼容是批次级失败，不降级为单会话 issue；会话错配、404、重试耗尽和响应解码失败才按条隔离。

## Alternatives considered

- 把上游响应当作 FastAPI OpenAPI：拒绝。出站客户端契约与本地 API 生命周期不同，会让前端生成物混入不存在的 inbound 路由。
- 在 CI 连接真实上游：拒绝。M6 才负责真实接入，M2 的确定性依赖 mock transport。
- 为上游建立第二份 payload 表：拒绝。同一轨迹必须只有一份原文，幂等键和运行态游标才能一致。

## Consequences

M2 只能证明客户端契约与 mock 行为，不能宣称真实上游可用；M6 接入时必须按真实实现验证兼容性。

运行时新增 `httpx` 依赖；上游配置缺失时 pull 返回 `UPSTREAM_NOT_AVAILABLE`，不会部分启动。
