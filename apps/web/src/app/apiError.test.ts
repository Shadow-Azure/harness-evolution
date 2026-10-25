import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/http";
import { presentConflict } from "./apiError";

describe("global API error presentation", () => {
  it("presents a 409 RUN_BUSY as one non-blocking message", () => {
    const notify = vi.fn();

    expect(
      presentConflict(
        new ApiError(409, "RUN_BUSY", "已有任务正在运行"),
        notify,
      ),
    ).toBe(true);
    expect(notify).toHaveBeenCalledOnce();
    expect(notify).toHaveBeenCalledWith("已有任务正在运行");
  });

  it("leaves terminal and unknown failures for page-level states", () => {
    const notify = vi.fn();

    expect(
      presentConflict(new ApiError(500, "INTERNAL", "服务不可用"), notify),
    ).toBe(false);
    expect(presentConflict(new Error("unexpected"), notify)).toBe(false);
    expect(notify).not.toHaveBeenCalled();
  });
});
