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
