// @vitest-environment jsdom

import { flushPromises, mount } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { http, HttpResponse } from "msw";
import {
  afterAll,
  afterEach,
  beforeAll,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import { server } from "../../../test/server";
import SourceMatrix from "./SourceMatrix.vue";

const buckets = [
  { bucket: "2026-11-02", label: "11-02", self: 1, discovery: 1, total: 2 },
  { bucket: "2026-11-09", label: "11-09", self: 1, discovery: 0, total: 1 },
];

const sources = [
  { object: "alpha", total: 2, self: 1, discovery: 1, sessions: 2 },
  { object: "beta", total: 1, self: 1, discovery: 0, sessions: 1 },
];

const requests: string[] = [];

function json(items: unknown[]) {
  return HttpResponse.json({ items });
}

function mountMatrix(overrides: Record<string, unknown> = {}) {
  return mount(SourceMatrix, {
    props: {
      workspaceId: "ws-test",
      sources,
      buckets,
      grain: "week",
      filters: { range: 90, objects: [] },
      window: { from: "2026-11-01", to: "2026-11-30" },
      ...overrides,
    },
    global: {
      plugins: [
        [
          VueQueryPlugin,
          {
            queryClient: new QueryClient({
              defaultOptions: { queries: { gcTime: 0, retry: false } },
            }),
          },
        ],
      ],
    },
  });
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  requests.length = 0;
  server.resetHandlers();
});
afterAll(() => server.close());

describe("overview source × time matrix", () => {
  it("loads one aggregate read per bucket only after expanding", async () => {
    server.use(
      http.get("/api/workspaces/:wid/overview/sources", ({ request }) => {
        requests.push(request.url);
        const from = new URL(request.url).searchParams.get("from");
        if (from === "2026-11-02") {
          return json([
            { object: "alpha", total: 2, self: 1, discovery: 1, sessions: 2 },
            { object: "beta", total: 1, self: 1, discovery: 0, sessions: 1 },
          ]);
        }
        if (from === "2026-11-09") {
          return json([
            { object: "alpha", total: 1, self: 1, discovery: 0, sessions: 1 },
          ]);
        }
        return json([]);
      }),
    );
    const wrapper = mountMatrix();

    expect(wrapper.find("[data-testid='ov-matrix-body']").exists()).toBe(false);
    expect(requests).toHaveLength(0);

    await wrapper.get("[data-testid='ov-matrix-toggle']").trigger("click");
    await vi.waitFor(() => {
      expect(requests).toHaveLength(2);
    });
    await flushPromises();

    const windows = requests.map((url) => new URL(url));
    expect(windows.map((url) => url.searchParams.get("from"))).toEqual([
      "2026-11-02",
      "2026-11-09",
    ]);
    expect(windows.map((url) => url.searchParams.get("to"))).toEqual([
      "2026-11-08",
      "2026-11-15",
    ]);
    expect(windows.every((url) => !url.searchParams.has("range"))).toBe(true);

    const rows = wrapper.findAll("[data-testid='ov-matrix-row']");
    expect(rows).toHaveLength(2);
    const alpha = wrapper.get("[data-object='alpha']");
    expect(alpha.findAll("td").map((cell) => cell.text())).toEqual([
      "自身 1 / 前置 1",
      "自身 1 / 前置 0",
      "2 / 1",
    ]);
    const beta = wrapper.get("[data-object='beta']");
    expect(beta.findAll("td").map((cell) => cell.text())).toEqual([
      "自身 1 / 前置 0",
      "自身 0 / 前置 0",
      "1 / 0",
    ]);

    await wrapper.get("[data-testid='ov-matrix-toggle']").trigger("click");
    expect(wrapper.find("[data-testid='ov-matrix-body']").exists()).toBe(false);
  });

  it("clips the first and last bucket to the active overview window", async () => {
    server.use(
      http.get("/api/workspaces/:wid/overview/sources", ({ request }) => {
        requests.push(request.url);
        return json([
          { object: "alpha", total: 1, self: 1, discovery: 0, sessions: 1 },
        ]);
      }),
    );
    const wrapper = mountMatrix({
      window: { from: "2026-11-05", to: "2026-11-12" },
    });

    await wrapper.get("[data-testid='ov-matrix-toggle']").trigger("click");
    await vi.waitFor(() => {
      expect(requests).toHaveLength(2);
    });
    const windows = requests.map((url) => new URL(url));
    expect(windows.map((url) => [url.searchParams.get("from"), url.searchParams.get("to")]))
      .toEqual([
        ["2026-11-05", "2026-11-08"],
        ["2026-11-09", "2026-11-12"],
      ]);
  });

  it("waits for the authoritative window instead of reading unclipped buckets", async () => {
    const wrapper = mountMatrix({ window: null });

    await wrapper.get("[data-testid='ov-matrix-toggle']").trigger("click");
    await flushPromises();

    expect(
      wrapper.find("[data-testid='ov-matrix-window-unavailable']").exists(),
    ).toBe(true);
    expect(requests).toHaveLength(0);
  });

  it("asks for a coarser grain instead of issuing a dense read storm", async () => {
    const dense = Array.from({ length: 32 }, (_, index) => ({
      bucket: `2026-08-${String(index + 1).padStart(2, "0")}`,
      label: `08-${String(index + 1).padStart(2, "0")}`,
      self: 0,
      discovery: 0,
      total: 0,
    }));
    const wrapper = mountMatrix({ buckets: dense });

    await wrapper.get("[data-testid='ov-matrix-toggle']").trigger("click");
    await flushPromises();

    expect(wrapper.get("[data-testid='ov-matrix-dense']").text()).toContain(
      "切换为周或月粒度",
    );
    expect(requests).toHaveLength(0);
  });

  it("shows an honest empty state when every bucket is empty", async () => {
    server.use(
      http.get("/api/workspaces/:wid/overview/sources", () => json([])),
    );
    const wrapper = mountMatrix();

    await wrapper.get("[data-testid='ov-matrix-toggle']").trigger("click");
    await vi.waitFor(() => {
      expect(wrapper.find("[data-testid='ov-matrix-empty']").exists()).toBe(true);
    });
    expect(wrapper.findAll("[data-testid='ov-matrix-row']")).toHaveLength(0);
  });

  it("shows a retryable error when one bucket read fails", async () => {
    let failed = false;
    server.use(
      http.get("/api/workspaces/:wid/overview/sources", ({ request }) => {
        const from = new URL(request.url).searchParams.get("from");
        if (from === "2026-11-09" && !failed) {
          failed = true;
          return HttpResponse.json(
            { error: { code: "INTERNAL", message: "boom", details: {} } },
            { status: 500 },
          );
        }
        return json([
          { object: "alpha", total: 1, self: 1, discovery: 0, sessions: 1 },
        ]);
      }),
    );
    const wrapper = mountMatrix();

    await wrapper.get("[data-testid='ov-matrix-toggle']").trigger("click");
    await vi.waitFor(() => {
      expect(wrapper.find("[data-testid='ov-matrix-error']").exists()).toBe(true);
    });
    expect(wrapper.get("[data-testid='ov-matrix-error']").text()).toContain(
      "INTERNAL",
    );

    await wrapper.get("[data-testid='ov-matrix-error'] button").trigger("click");
    await vi.waitFor(() => {
      expect(wrapper.findAll("[data-testid='ov-matrix-row']").length).toBeGreaterThan(0);
    });
  });

  it("does not render the entry without sources or buckets", () => {
    expect(
      mountMatrix({ sources: [] }).find("[data-testid='ov-source-matrix']").exists(),
    ).toBe(false);
    expect(
      mountMatrix({ buckets: [] }).find("[data-testid='ov-source-matrix']").exists(),
    ).toBe(false);
  });
});
