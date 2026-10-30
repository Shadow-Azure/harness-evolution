/**
 * Translate a durable acquisition status into user-facing copy.
 * @param status Current acquisition status.
 * @returns Chinese status label.
 */
export function syncStatusLabel(status: string): string {
  switch (status) {
    case "queued":
      return "排队中";
    case "running":
      return "同步中";
    case "completed":
      return "已完成";
    case "failed":
      return "失败";
    case "interrupted":
      return "已中断";
    default:
      return "空闲";
  }
}

/**
 * Wait between durable job polls.
 * @param milliseconds Delay duration.
 * @returns Promise resolved after the delay.
 */
export function waitForSyncPoll(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

/**
 * Translate a stable sync issue code into user-facing copy.
 * @param code Machine-readable replay issue code.
 * @returns Chinese issue summary.
 */
export function syncErrorLabel(code: string): string {
  switch (code) {
    case "INVALID_JSONL_LINE":
      return "有一行轨迹无法解析";
    case "MISSING_PAYLOAD_SOURCE":
      return "源数据缺失";
    case "MISSING_PARENT_TOOL_USE_ID":
      return "部分 Agent 缺少父调用";
    case "SYNC_PROGRESS_FAILED":
      return "进度通知失败";
    default:
      return "同步发现问题";
  }
}

/**
 * Translate a bad-case root-sync state into user-facing copy.
 * @param status Durable root-sync state.
 * @returns Chinese status label.
 */
export function badCaseSyncStatusLabel(status: string): string {
  switch (status) {
    case "queued":
      return "排队中";
    case "running":
      return "补齐中";
    case "failed":
      return "补齐失败";
    case "unavailable":
      return "未配置轨迹查询服务";
    default:
      return "空闲";
  }
}

/**
 * Translate a catalog sync state into user-facing copy.
 * @param status Durable catalog sync state.
 * @returns Chinese status label.
 */
export function catalogSyncStatusLabel(status: string): string {
  switch (status) {
    case "queued":
      return "排队中";
    case "running":
      return "同步中";
    case "failed":
      return "同步失败";
    case "unavailable":
      return "未配置坏例查询服务";
    default:
      return "空闲";
  }
}

/**
 * Translate a stable catalog sync error code into user-facing copy.
 * @param code Machine-readable catalog error code.
 * @returns Chinese failure label.
 */
export function catalogSyncErrorLabel(code: string | null): string {
  switch (code) {
    case "BAD_CASE_QUERY_TIMEOUT":
      return "坏例查询超时";
    case "BAD_CASE_QUERY_UNAUTHORIZED":
      return "坏例查询鉴权失败";
    case "BAD_CASE_QUERY_INVALID_RESPONSE":
      return "坏例查询响应异常";
    case "BAD_CASE_QUERY_REQUEST_FAILED":
      return "坏例查询请求失败";
    case "BAD_CASE_CATALOG_SYNC_INTERRUPTED":
      return "上次同步中断";
    case "BAD_CASE_CATALOG_SYNC_FAILED":
      return "目录同步失败";
    default:
      return "目录同步失败";
  }
}

/**
 * Translate a stable root-sync error code into user-facing copy.
 * @param code Machine-readable root-sync error code.
 * @returns Chinese failure label.
 */
export function badCaseSyncErrorLabel(code: string | null): string {
  switch (code) {
    case "SESSION_QUERY_TIMEOUT":
      return "轨迹查询超时";
    case "SESSION_QUERY_UNAUTHORIZED":
      return "轨迹查询鉴权失败";
    case "SESSION_QUERY_INVALID_RESPONSE":
      return "轨迹查询响应异常";
    case "SESSION_QUERY_REQUEST_FAILED":
      return "轨迹查询请求失败";
    case "TRAVERSAL_LIMIT_EXCEEDED":
      return "会话树超过上限";
    case "BAD_CASE_SYNC_TIME_BUDGET":
      return "单批时间预算用尽";
    case "TRAJECTORY_EMPTY":
      return "轨迹为空";
    default:
      return "轨迹补齐失败";
  }
}
