// @vitest-environment jsdom

import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

const testGlobal = globalThis as typeof globalThis & {
  IS_REACT_ACT_ENVIRONMENT: boolean;
};

testGlobal.IS_REACT_ACT_ENVIRONMENT = true;

afterEach(() => {
  document.body.innerHTML = "";
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

async function renderApp(): Promise<{ container: HTMLDivElement; root: ReturnType<typeof createRoot> }> {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<App />);
    await Promise.resolve();
  });
  return { container, root };
}

describe("App", () => {
  it("renders the connected state from the health response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          ok: true,
          phase: "scaffold",
          service: "harness-evolution"
        })
      })
    );

    const { container, root } = await renderApp();

    expect(container.textContent).toContain("API 已连接");
    expect(container.textContent).toContain("FastAPI + Python");
    await act(async () => root.unmount());
  });

  it("renders the failure state when the health request rejects", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    const { container, root } = await renderApp();

    expect(container.textContent).toContain("API 未连接");
    await act(async () => root.unmount());
  });

  it("renders the loading state while the health request is pending", async () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => undefined)));

    const { container, root } = await renderApp();

    expect(container.textContent).toContain("连接中…");
    await act(async () => root.unmount());
  });
});
