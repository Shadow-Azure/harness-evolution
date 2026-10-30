import { describe, expect, it } from "vitest";

import {
  badCaseSyncErrorLabel,
  badCaseSyncStatusLabel
} from "./syncStatus";

describe("bad-case sync status labels", () => {
  it("distinguishes running, failed, and unavailable states", () => {
    expect(badCaseSyncStatusLabel("running")).toBe("补齐中");
    expect(badCaseSyncStatusLabel("failed")).toBe("补齐失败");
    expect(badCaseSyncStatusLabel("unavailable")).toBe("未配置轨迹查询服务");
  });

  it("maps stable root-sync error codes to readable copy", () => {
    expect(badCaseSyncErrorLabel("SESSION_QUERY_TIMEOUT")).toBe("轨迹查询超时");
    expect(badCaseSyncErrorLabel("TRAVERSAL_LIMIT_EXCEEDED")).toBe("会话树超过上限");
    expect(badCaseSyncErrorLabel(null)).toBe("轨迹补齐失败");
  });
});
