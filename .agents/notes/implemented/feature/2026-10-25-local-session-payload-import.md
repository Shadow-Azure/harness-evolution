# Agent Note: 本地 session payload 导入

Status: implemented

[English](2026-10-25-local-session-payload-import.en.md) | 中文

## Problem

开发机上的 Claude Code session 是后续归一化的真实输入，但目录里同时存在 payload JSONL、Agent sidecar meta、工具结果和错误文本。若导入器直接扫描所有文件或信任文件名，就可能写入错误 Agent、把非 payload 状态带进数据库，或者在 re-import 时覆盖归一化进度。完整正文又不能进入 CI、日志或 Git。

## Decision

- 开发导入只消费 root JSONL，以及每个 root 下 `subagents/agent-*.jsonl` 与其精确配对的 `.meta.json`；工具结果、marker 和错误文本保留在本地但不读取。JSONL framing 只识别 LF/CRLF，字符串内的 Unicode 行分隔符保留为正文。root 主 Agent 的 `agent_id` 等于 root session id；Claude 允许部分 root 行省略 `sessionId`，但至少一条必须声明，所有已声明值都必须与文件名一致。subagent 的 `agentId` 同时校验 JSONL 与文件名；Agent 身份以 `(root_session_id, agent_id)` 为复合键，允许不同 root 复用同一个 provider agent id。
- JSONL 原文以 `(root_session_id, agent_id)` stable key 一次性写入 `trajectory_payloads`，hash 与行数从原始字节派生；`agent_meta` 只存通过封闭 schema 的 subagent meta，长度上限与后续 `agents` 表一致。全部 payload 先扫描验证，再用单一事务写入，失败不留部分行。
- `source_records` 只建立处理索引，`processed_*` 与 `last_sync_run_id` 保持未处理；`received_at` 记录首次发现时间，payload 的 `updated_at` 才来自源文件写入时间。双方言时间统一到 MySQL `DATETIME` 的秒精度。重复导入未变内容零写入，内容变化只更新对应 payload，不覆盖归一化运行态或首次发现时间。
- 本地目录与 `data/harness-evolution.sqlite` 均 gitignored；CLI 对路径只做不跟随 symlink 的绝对化，source root symlink 在扫描前拒绝。命令只输出 root/JSONL/subagent/payload 聚合，不输出正文、源路径或连接串，文件系统失败也会移除路径详情。生产与 live phase 在扫描和连接数据库前拒绝。`verify-local` 验证本地身份集合已完整落库，允许共享数据库存在其他来源的额外行。

## Alternatives considered

- 把所有本地文件复制到 fixtures：实现集中，但真实正文会进入仓库，且 CI 依赖个人数据；否决。
- 信任文件名直接入库：解析更快，但文件名与 JSONL 身份不一致时会污染 Agent 树；否决。
- 将 `source_records` 标记为已处理：可让本地 seed 看起来完整，却会让后续归一化跳过 payload；否决。
- 只插入不更新：同内容幂等，但源 payload 修正后永远陈旧；否决。

## Consequences

- 本地真实导入的验收聚合为 4 roots、66 JSONL、62 subagents、66 payload rows，约 49.5 MiB；CI 只用小体积合成目录验证同一契约。
- Claude 目录新增合法 sidecar 类型时需要评估是否影响 payload 配对；非 payload 文件默认忽略，不成为运行时数据源。
- 归一化、parser version 与会话树构建属于后续 acquisition issue；本导入只准备原始 payload 和未处理索引。
