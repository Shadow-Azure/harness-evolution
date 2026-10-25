import type { App } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installGlobalErrorHandler } from "./globalError";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("global Vue error handling", () => {
  it("reports once and presents a generic inline message", () => {
    const app = { config: {} } as App;
    const notify = vi.fn();
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

    installGlobalErrorHandler(app, notify);
    expect(app.config.errorHandler).toBeTypeOf("function");

    app.config.errorHandler?.(
      new Error("secret backend detail"),
      null,
      "component render",
    );

    expect(consoleError).toHaveBeenCalledTimes(1);
    expect(notify).toHaveBeenCalledTimes(1);
    expect(notify).toHaveBeenCalledWith("操作失败，请稍后重试");
    expect(notify.mock.calls[0]?.[0]).not.toContain("secret backend detail");
  });
});
