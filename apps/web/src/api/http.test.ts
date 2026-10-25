import { afterEach, describe, expect, it, vi } from "vitest";

import {
  request,
  resetHttpAuthHandlers,
  setAccessTokenProvider,
  setAuthExpiredHandler,
  setPasswordChangeHandler,
  setRefreshHandler,
} from "./http";

function jsonResponse(body: unknown, status = 200): Response {
  return Response.json(body, { status });
}

afterEach(() => {
  vi.unstubAllGlobals();
  resetHttpAuthHandlers();
});

describe("request", () => {
  it("decodes an accepted JSON response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ ok: true })));

    await expect(request<{ ok: boolean }>("/api/example")).resolves.toEqual({ ok: true });
  });

  it("injects the in-memory bearer token while preserving caller headers", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    setAccessTokenProvider(() => "access-token");

    await request("/api/example", {
      headers: { "x-request-id": "request-1" },
    });

    const headers = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    expect(headers.get("authorization")).toBe("Bearer access-token");
    expect(headers.get("x-request-id")).toBe("request-1");
  });

  it("accepts 201 and 204 without decoding a missing body", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(jsonResponse({ id: "created" }, 201))
        .mockResolvedValueOnce(new Response(null, { status: 204 })),
    );

    await expect(request<{ id: string }>("/api/created")).resolves.toEqual({ id: "created" });
    await expect(request<void>("/api/empty")).resolves.toBeUndefined();
  });

  it("surfaces the shared error envelope and details", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            error: {
              code: "VALIDATION_INVALID",
              message: "invalid request",
              details: { field: "username" },
            },
          },
          422,
        ),
      ),
    );

    await expect(request("/api/example")).rejects.toMatchObject({
      status: 422,
      code: "VALIDATION_INVALID",
      message: "invalid request",
      details: { field: "username" },
    });
  });

  it("falls back to a stable code for a non-JSON failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("<html>gateway error</html>", { status: 500 })),
    );

    await expect(request("/api/example")).rejects.toMatchObject({
      code: "HTTP_ERROR",
      status: 500,
    });
  });

  it("refreshes once for concurrent 401 responses and replays with the original request", async () => {
    let accessToken = "expired";
    let refreshCalls = 0;
    const fetchMock = vi.fn(async (_path: string, init?: RequestInit) => {
      const headers = new Headers(init?.headers);
      if (headers.get("authorization") === "Bearer expired") {
        return jsonResponse(
          { error: { code: "AUTH_EXPIRED", message: "expired" } },
          401,
        );
      }
      return jsonResponse({ body: init?.body, method: init?.method });
    });
    vi.stubGlobal("fetch", fetchMock);
    setAccessTokenProvider(() => accessToken);
    setRefreshHandler(async () => {
      refreshCalls += 1;
      await Promise.resolve();
      accessToken = "fresh";
      return true;
    });

    const init = {
      body: JSON.stringify({ value: 1 }),
      headers: { "content-type": "application/json" },
      method: "POST",
    };
    const [first, second] = await Promise.all([
      request("/api/example", init),
      request("/api/example", init),
    ]);

    expect(refreshCalls).toBe(1);
    expect(first).toEqual({ body: init.body, method: "POST" });
    expect(second).toEqual({ body: init.body, method: "POST" });
  });

  it("never refreshes public auth requests", async () => {
    const refresh = vi.fn().mockResolvedValue(true);
    const expired = vi.fn();
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        jsonResponse({ error: { code: "AUTH_EXPIRED", message: "expired" } }, 401),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    setRefreshHandler(refresh);
    setAuthExpiredHandler(expired);

    await expect(request("/api/auth/login", { method: "POST" })).rejects.toMatchObject({
      code: "AUTH_EXPIRED",
    });
    await expect(request("/api/auth/refresh", { method: "POST" })).rejects.toMatchObject({
      code: "AUTH_EXPIRED",
    });
    expect(refresh).not.toHaveBeenCalled();
    expect(expired).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("refreshes once and replays a protected auth request with an expired access token", async () => {
    let accessToken = "expired";
    let refreshCalls = 0;
    const fetchMock = vi.fn(async (_path: string, init?: RequestInit) => {
      const authorization = new Headers(init?.headers).get("authorization");
      if (authorization === "Bearer expired") {
        return jsonResponse({ error: { code: "AUTH_EXPIRED", message: "expired" } }, 401);
      }
      return jsonResponse({
        id: "u-1",
        username: "operator",
        displayName: "Operator",
        role: "member",
        mustChangePassword: false,
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    setAccessTokenProvider(() => accessToken);
    setRefreshHandler(async () => {
      refreshCalls += 1;
      accessToken = "fresh";
      return true;
    });

    await expect(request("/api/auth/me")).resolves.toMatchObject({ id: "u-1" });

    expect(refreshCalls).toBe(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(new Headers(fetchMock.mock.calls[1]?.[1]?.headers).get("authorization")).toBe(
      "Bearer fresh",
    );
  });

  it("does not refresh or expire the session for an authentication credential failure", async () => {
    const refresh = vi.fn().mockResolvedValue(true);
    const expired = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ error: { code: "AUTH_INVALID", message: "bad credentials" } }, 401),
    );
    vi.stubGlobal("fetch", fetchMock);
    setRefreshHandler(refresh);
    setAuthExpiredHandler(expired);

    await expect(request("/api/auth/change-password", { method: "POST" })).rejects.toMatchObject({
      code: "AUTH_INVALID",
    });

    expect(refresh).not.toHaveBeenCalled();
    expect(expired).not.toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("clears auth when a refreshed request is still unauthorized", async () => {
    const expired = vi.fn();
    let refreshCalls = 0;
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(
        jsonResponse({ error: { code: "AUTH_EXPIRED", message: "expired" } }, 401),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    setRefreshHandler(async () => {
      refreshCalls += 1;
      return true;
    });
    setAuthExpiredHandler(expired);

    await expect(request("/api/users")).rejects.toMatchObject({ code: "AUTH_EXPIRED" });

    expect(refreshCalls).toBe(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(expired).toHaveBeenCalledOnce();
    expect(expired).toHaveBeenCalledWith("/");
  });

  it("clears auth through the injected expired handler when refresh fails", async () => {
    const expired = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ error: { code: "AUTH_EXPIRED", message: "expired" } }, 401),
      ),
    );
    setRefreshHandler(async () => false);
    setAuthExpiredHandler(expired);

    await expect(request("/api/example")).rejects.toMatchObject({ code: "AUTH_EXPIRED" });
    expect(expired).toHaveBeenCalledWith("/");
  });

  it("routes a forced-password-change response without treating it as a page error", async () => {
    const passwordChange = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          {
            error: {
              code: "PASSWORD_CHANGE_REQUIRED",
              message: "password change required",
            },
          },
          403,
        ),
      ),
    );
    setPasswordChangeHandler(passwordChange);

    await expect(request("/api/users")).rejects.toMatchObject({
      code: "PASSWORD_CHANGE_REQUIRED",
    });
    expect(passwordChange).toHaveBeenCalledWith("/");
  });

  it("forwards abort signals", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await request("/api/example", { signal: controller.signal });

    expect(fetchMock.mock.calls[0]?.[1]?.signal).toBe(controller.signal);
  });
});
