import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchAppConfig } from "./appConfig";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("app-config API", () => {
  it("returns the configured brand pair", async () => {
    const payload = {
      brand: {
        name: "Acme Diagnostics",
        subtitle: "Acme Self-Evolution",
      },
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(payload)));

    await expect(fetchAppConfig()).resolves.toEqual(payload);
  });

  it("rejects a payload without the subtitle", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(Response.json({ brand: { name: "Acme Diagnostics" } })),
    );

    await expect(fetchAppConfig()).rejects.toMatchObject({
      code: "INVALID_RESPONSE",
      status: 200,
    });
  });

  it("rejects a blank brand field", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        Response.json({
          brand: { name: "   ", subtitle: "Acme Self-Evolution" },
        }),
      ),
    );

    await expect(fetchAppConfig()).rejects.toMatchObject({
      code: "INVALID_RESPONSE",
      status: 200,
    });
  });

  it("rejects invalid JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("not-json", { status: 200 })),
    );

    await expect(fetchAppConfig()).rejects.toMatchObject({ code: "INVALID_JSON" });
  });

  it("turns transport failures into ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    await expect(fetchAppConfig()).rejects.toMatchObject({ code: "NETWORK_ERROR" });
  });
});
