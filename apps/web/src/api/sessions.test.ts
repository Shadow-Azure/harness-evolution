// @vitest-environment jsdom

import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { getSession, listSessions } from "./sessions";
import { server } from "../test/server";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("sessions api", () => {
  it("encodes list filters without reordering the server response", async () => {
    let requestUrl = "";
    server.use(
      http.get("/api/sessions", ({ request }) => {
        requestUrl = request.url;
        return HttpResponse.json({
          items: [
            {
              id: "s-2",
              title: "Second",
              short: "Second",
              repo: "repo",
              startedAt: "2026-10-20T08:00:00+08:00",
              durationSeconds: 12,
              model: "model",
              status: "ok",
              skills: [],
              stats: {
                agents: 0,
                badCases: 0,
                badCasesPer100Messages: 0,
                errors: 0,
                failPer100Messages: 0,
                messages: 1,
                tokens: 10,
                tools: 0,
                userTurns: 1,
              },
            },
          ],
        });
      }),
    );

    const result = await listSessions({
      q: "a&b",
      status: "problem",
      sort: "agents",
      limit: 4,
    });

    expect(new URL(requestUrl).searchParams.get("q")).toBe("a&b");
    expect(new URL(requestUrl).searchParams.get("status")).toBe("problem");
    expect(new URL(requestUrl).searchParams.get("sort")).toBe("agents");
    expect(result.items.map((item) => item.id)).toEqual(["s-2"]);
  });

  it("URL-encodes a session id", async () => {
    let pathname = "";
    server.use(
      http.get("/api/sessions/:id", ({ request }) => {
        pathname = new URL(request.url).pathname;
        return HttpResponse.json({});
      }),
    );

    await getSession("root/with space");
    expect(pathname).toBe("/api/sessions/root%2Fwith%20space");
  });
});
