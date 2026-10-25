import { describe, expect, it, vi } from "vitest";

import { request } from "./http";

describe("request", () => {
  it("decodes an accepted JSON response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ ok: true })));

    await expect(request<{ ok: boolean }>("/api/example")).resolves.toEqual({ ok: true });
  });

  it("normalizes rejected HTTP statuses before decoding", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("<html>gateway error</html>", { status: 500 }))
    );

    await expect(request("/api/example")).rejects.toMatchObject({
      code: "HTTP_ERROR",
      status: 500
    });
  });

  it("normalizes malformed accepted bodies", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("{not-json", { status: 200 }))
    );

    await expect(request("/api/example")).rejects.toMatchObject({ code: "INVALID_JSON" });
  });
});
