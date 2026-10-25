# Agent Note: 幂等 Agent 树重放

Status: implemented

[English](2026-10-25-idempotent-replay.en.md) | 中文

## Problem

会话树跨同一 root 的多个 Agent payload。只按单个 Agent 增量修写会让父子边、会话统计和用户轮次短暂不一致；以全局水位线跳过又会漏掉内容变化与 parser 升级。

## Decision

pending 按 source record 的 `processed_hash` 与 `parser_version` 判定，再按 `root_session_id` 分组。执行前读取该 root 全部当前 payload，完成纯 normalizer 与 Agent tree assembler；只有组装成功才打开单 root 事务。事务按事件、Agent、用户轮次、会话的 FK 顺序删除旧派生行，再写当前 canonical 快照并推进该 root 所有现存 source 游标；游标更新同步当前 payload 的 `line_count/kind/source_type`，保留 source 的 `id/received_at`。

hash 与 parser version 均未变化的 payload 不进入 pending，重复批次只记 skipped，不刷新 processed 时间。parser 升级即使 hash 相同也重放整个 root。结构失败保留旧树与该 root 的游标，其他 root 独立完成；可恢复坏行仍写树并将稳定脱敏 issue 写入 `sync_runs.errors`。`trajectory_payloads` 是只读输入，当前重放不因源文件消失而删除既有业务树。

## Alternatives considered

- 按单个 Agent 删除重写：会破坏跨 Agent 的父边和会话聚合版本一致性。
- 用全局 processed 水位线：无法表达组合键游标，也会漏掉旧 parser version。
- 结构失败时先清空旧树：用户会看到无法恢复的空洞，无法等待 payload 修复后自然重放。
- 每次重放都刷新 processed 时间：会让未变化输入产生伪写入，破坏幂等审计。

## Consequences

m2-06 与 m2-07 可以在本 service 外接 API、sync lock 和调度，不得复制删除重写规则。m5 的 run event projection 继续独立。root 内一次全量解析的内存成本随单会话 Agent 数增长；V1 单组织串行边界接受该成本，未来按规模再评估增量索引。
