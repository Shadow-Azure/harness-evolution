# Agent Note: bad_cases 根会话轨迹定时同步

Status: implemented

[English](2026-10-30-bad-case-session-sync.en.md) | 中文

## Problem

`bad_cases.bad_case_session_id` 指向问题所属的根会话，但本服务没有保证该根会话的原始轨迹已经进入 `trajectory_payloads`。原先进库只有本地导入与管理员手动 pull 两条路径，都要求操作者知道 session id 或时间窗；bad_cases 增长后，问题详情、执行流图和自进化启动会因缺 payload 而看不到会话。查询服务又只提供“直接子 sessionId”的一层枚举与“单 agent 轨迹”的 NDJSON 下载，且后者禁止并发，无法复用现有“一次拿整棵 package”的 pull 契约。

## Decision

新增 `bad_case_root_sync` 状态表与 `bad_case_root_sync` 定时任务：从 `bad_cases` 的 distinct 根会话出发做 LEFT JOIN，选未同步、失败到期或租约过期的 root；claim 后按接口 1 逐层展开，按接口 2 串行取每个 agent 的 NDJSON，写 `trajectory_payloads`（`source_type=http_api`，subagent 的 `agent_meta={"parentAgentId": ...}`），再复用共享重放。`synced` 表示 payload 已完整写入，重放失败由现有 sync 审计承接，不回滚状态。重叠策略是跳过：tick 发现活跃 `bad_case_root_sync` job 就不提交，单 job 受批量与时间预算约束，下一 tick 按状态表续跑；不排队、不取消、不并行。状态表行在 root 从 bad_cases 消失后保留作审计，但不计入当前统计；没有状态行的新 root 计入 `total` 与 `unsynced` 并被候选查询选中。

## Alternatives considered

“活跃时排队一个后续 job”被否：定时器本身就是后续机制，排队只会制造重复扫描与重复 job；“取消上一个”被否：已写入 payload 是有效进度，接口 2 又是串行调用，取消纯浪费；“多 job 并行 + per-root claim”被否：接口 2 禁止并发，并行没有吞吐收益，反而需要跨进程锁。上线时按 `trajectory_payloads` 主行直接把 root 标 `synced` 被否：无法确认 subagent 完整性，会让“已同步”长期说谎；接受首轮重拉，把成本摊到批量与时间预算里。继续扩展既有“整包 pull”也被否：查询服务不返回整包，且没有 `agent_meta`，只能另建客户端。

## Consequences

新增服务自有表、迁移、job kind、配置、状态接口与顶栏展示；生产部署多一张表，手动 pull 保持不变。首轮会把已有 payload 的 root 也重拉一次，历史量大时由批量/时间预算摊到多个 tick；多实例部署仍需要跨进程锁与跨进程串行信号量，本版按单实例设计。subagent 没有 `toolUseId`，只能按 `parentAgentId` 挂到父 agent 节点，图的边精度低于本地导入；现有 pull 的 `parentToolUseId` / `toolUseId` 键名不一致在同批修正。`agent_count` 记录该 root 在 payload 表的实际行数（含 main），只用于诊断，不参与已同步统计。
