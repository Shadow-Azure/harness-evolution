import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/http";
import { formatApiError, presentConflict } from "./apiError";

describe("global API error presentation", () => {
  it("formats validation details into field locations and fixes", () => {
    const formatted = formatApiError(
      new ApiError(
        422,
        "VALIDATION_INVALID",
        "request validation failed",
        {
          errors: [
            {
              loc: ["body", "validationProjectId"],
              msg: "String should have at least 1 character",
              type: "string_too_short",
            },
            {
              loc: ["query", "unknownField"],
              msg: "Field required",
              type: "missing",
            },
          ],
        },
      ),
    );

    expect(formatted.message).toBe(
      "请检查以下输入：验证集测试工程 ID 不能为空，请填写后再试；查询参数不能为空，请检查输入后再试。",
    );
    expect(formatted.fieldErrors).toEqual({
      validationProjectId: "验证集测试工程 ID 不能为空，请填写后再试。",
      unknownField: "查询参数不能为空，请检查输入后再试。",
    });
    expect(formatted.message).not.toContain("String should");
    expect(formatted.message).not.toContain("Field required");
  });

  it("maps stable transport failures without exposing backend phrases", () => {
    expect(
      formatApiError(new ApiError(0, "NETWORK_ERROR", "API is unreachable")).message,
    ).toBe("网络连接不可用，请检查网络后重试。");
    expect(
      formatApiError(new ApiError(403, "AUTH_REQUIRED", "not authenticated")).message,
    ).toBe("当前账号没有执行此操作的权限，请联系管理员。");
    expect(
      formatApiError(new ApiError(500, "INTERNAL", "internal server error")).message,
    ).toBe("服务暂时不可用，请稍后重试；若持续失败请联系管理员。");
  });

  it("keeps operation context when validation details are unavailable", () => {
    expect(
      formatApiError(
        new ApiError(422, "VALIDATION_INVALID", "request validation failed"),
        "保存配置失败",
      ).message,
    ).toBe("保存配置失败，请检查输入后重试。");
    expect(
      formatApiError(new ApiError(409, "RUN_BUSY", "target is in use")).message,
    ).toBe("已有任务正在运行，请等待当前任务结束后重试。");
    expect(
      formatApiError(new Error("unexpected"), "立即处理失败").message,
    ).toBe("立即处理失败，请稍后重试。");
  });

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

  it("leaves a page-handled bad-case conflict to its blocking error state", () => {
    const notify = vi.fn();

    expect(
      presentConflict(
        new ApiError(
          409,
          "BAD_CASE_SESSION_MISMATCH",
          "bad case does not belong to the requested session",
        ),
        notify,
      ),
    ).toBe(false);
    expect(notify).not.toHaveBeenCalled();
  });

  it("leaves target-in-use deletion feedback to the configuration page", () => {
    const notify = vi.fn();

    expect(
      presentConflict(
        new ApiError(409, "TARGET_IN_USE", "target is in use"),
        notify,
      ),
    ).toBe(false);
    expect(notify).not.toHaveBeenCalled();
  });

  it("leaves duplicate target feedback to the configuration form", () => {
    const notify = vi.fn();

    expect(
      presentConflict(
        new ApiError(409, "TARGET_EXISTS", "target already exists"),
        notify,
      ),
    ).toBe(false);
    expect(notify).not.toHaveBeenCalled();
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
