# Agent Note: bad case 无 Session 时表达轨迹状态

Status: implemented

[English](2026-11-17-bad-case-session-trace-status.en.md) | 中文

## Problem

生产 bad case 列表能读出已上报的行，但点开详情返回 `404 BAD_CASE_NOT_FOUND`，前端显示「问题不存在或已删除」。真实原因不是行缺失，而是 root-sync 没有拿到可用的 `sessionSource`，回退到未配置的全局查询后以 `SESSION_QUERY_UNAVAILABLE` 失败，Session 从未落库；旧读模型把「case 存在但 Session 不在」折叠成「case 不存在」。

同一条 case 的读口径因此不一致：总览直接读 `bad_cases`，Session 列表返回空并计 `pendingSessions`，详情却是 404。运维也无法区分同步中、同步失败、上游无轨迹和真正删除，root-sync 还会对确定性失败反复走 1m/5m/15m/1h 退避。

## Decision

存在性以 `bad_cases` 行为准，轨迹就绪是另一个派生维度。`service/bad_cases/session_status.py` 把 `bad_case_root_sync` 与 Session 是否可读映射为五个公开状态：`ready/pending/syncing/failed/unavailable`；总览列表批量读同一页 root 的 sync state 和 Session 存在性，详情先用 case-only 查询判定 404，再判定轨迹。

详情仅在 case 行缺失时返回 `404 BAD_CASE_NOT_FOUND`；存在但 Session 未就绪时返回 `409 BAD_CASE_SESSION_PENDING`（pending/syncing）或 `503 BAD_CASE_SESSION_UNAVAILABLE`（failed/unavailable），`details` 带 `syncStatus/lastError/retryable/nextRetryAt/lastAttemptAt` 与 case 身份，前端据此渲染状态面板。列表项同步暴露同一组字段，未就绪行不再作为错误详情深链。

确定性失败（`SESSION_QUERY_UNAVAILABLE`、鉴权/版本不兼容、不支持的 runtime、空轨迹等）标记 `retryable=false` 并退出调度候选，避免无意义退避；没有任何可用 source 时所有未就绪状态都报 `retryable=false`。启动时若存在可用 source，把这些行复位为 pending，作为配置变化后的重新触发入口。真正的 404 语义与既有 happy path 不变。

## Alternatives considered

- 新增持久化 `unavailable/blocked` 状态和迁移：能直接表达阻塞，但本 issue 不需要新数据，且会增加状态机与回填面；先从现有字段派生，等平台侧 `traceAvailable/noTrace` 成为稳定契约再考虑落库。
- 详情继续 404 但附 `reason`：改动最小，却把「未就绪」继续伪装成「不存在」，前端与第三方调用方仍会误判数据丢失。
- 列表逐行查询 `bad_case_root_sync`：实现直接但形成 N+1；按页批量读 root 状态与 Session 存在性更符合总览的分页读路径。
- 保留确定性失败的自动重试：能让配置修复后自动恢复，但继续产生无意义任务与噪声日志；改为启动复位 + 手动同步入口。

## Consequences

- API 新增两个稳定错误码，OpenAPI/TS 类型与错误矩阵同步更新；旧客户端仍可把 404 理解为缺失，但需要处理 409/503 才能看到状态。
- 列表多两次批量查询（sync state、Session 存在性），与分页大小无关；详情多一次 case-only 查询。
- 确定性失败在两处可见口径不完全一致：`acquisition.status` 的 `failed` 计数仍包含它们，因为持久化状态仍是 `failed`；重启且存在可用 source 时会短暂显示 pending，直到下一次同步结果。
- 无 Session 的既有数据不需要回填，下一次读取自动获得派生状态。
