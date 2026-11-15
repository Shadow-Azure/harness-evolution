// @vitest-environment jsdom

import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { createPinia, setActivePinia } from "pinia";
import { http, HttpResponse } from "msw";
import {
  afterAll,
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import OverviewPage from "./Index.vue";
import { createAppRouter } from "../../router";
import { server } from "../../test/server";
import { signInWithWorkspace, testWorkspace, TEST_WORKSPACE_ID } from "../../test/auth";

const workspaceId = TEST_WORKSPACE_ID;
const ws = `/workspaces/${workspaceId}`;

const summary = {
  window: { from: "2026-08-19", to: "2026-11-16" },
  totals: {
    badCases: 3,
    self: 2,
    discovery: 1,
    sessions: 2,
    sources: 2,
    quota: 60,
    used: 3,
  },
  objects: ["deep-research", "workflow"],
};

const trend = {
  window: { from: "2026-08-19", to: "2026-11-16" },
  grain: "week",
  buckets: [
    { bucket: "2026-11-02", label: "11-02", self: 1, discovery: 0, total: 1 },
    { bucket: "2026-11-09", label: "11-09", self: 1, discovery: 1, total: 2 },
  ],
};

const sources = {
  items: [
    { object: "deep-research", total: 2, self: 1, discovery: 1, sessions: 2 },
    { object: "workflow", total: 1, self: 1, discovery: 0, sessions: 1 },
  ],
};

function caseRow(index: number) {
  return {
    badCaseId: `BC-HC-00${index}`,
    sessionId: `session-${index}`,
    objectName: index % 2 === 0 ? "deep-research" : "workflow",
    badCaseType: index % 2 === 0 ? "self" : "discovery",
    badCaseTypeLabel: index % 2 === 0 ? "自身存在问题" : "发现前置步骤问题",
    title: `Case title ${index}`,
    triggerAt: `2026-11-0${index}T08:00:00+08:00`,
    createdAt: `2026-11-0${index}T09:00:00+08:00`,
    attributionCount: index,
  };
}

const cases = {
  items: [caseRow(1), caseRow(2), caseRow(3)],
  total: 3,
  page: 1,
  pageSize: 8,
};

type RequestLog = {
  summary: string[];
  trend: string[];
  sources: string[];
  cases: string[];
};

let requests: RequestLog;
const mounted: VueWrapper[] = [];

function mockOverviewApi(overrides: Record<string, unknown> = {}) {
  server.use(
    http.get("/api/workspaces/:wid/overview/summary", ({ request }) => {
      requests.summary.push(request.url);
      return HttpResponse.json(overrides.summary ?? summary);
    }),
    http.get("/api/workspaces/:wid/overview/trend", ({ request }) => {
      requests.trend.push(request.url);
      return HttpResponse.json(overrides.trend ?? trend);
    }),
    http.get("/api/workspaces/:wid/overview/sources", ({ request }) => {
      requests.sources.push(request.url);
      return HttpResponse.json(overrides.sources ?? sources);
    }),
    http.get("/api/workspaces/:wid/bad-cases", ({ request }) => {
      requests.cases.push(request.url);
      return HttpResponse.json(overrides.cases ?? cases);
    }),
  );
}

async function mountPage(
  path = `${ws}/overview`,
  workspaces = [testWorkspace()],
) {
  const pinia = createPinia();
  setActivePinia(pinia);
  signInWithWorkspace(undefined, workspaces);
  const router = createAppRouter();
  await router.push(path);
  await router.isReady();
  const wrapper = mount(OverviewPage, {
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
        pinia,
        router,
      ],
    },
  });
  mounted.push(wrapper);
  await flushPromises();
  return { router, wrapper };
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  server.resetHandlers();
});
afterAll(() => server.close());

describe("workspace overview page", () => {
  beforeEach(() => {
    requests = { summary: [], trend: [], sources: [], cases: [] };
  });

  it("canonicalizes the landing URL and renders all six stats", async () => {
    mockOverviewApi();
    const { router, wrapper } = await mountPage();

    expect(router.currentRoute.value.query).toEqual({
      tab: "cases",
      range: "90",
      grain: "week",
    });
    expect(wrapper.find("[data-testid='overview-page']").exists()).toBe(true);
    expect(wrapper.get("[data-testid='ov-stat-badcases']").text()).toContain("3");
    expect(wrapper.get("[data-testid='ov-stat-self']").text()).toContain("2");
    expect(wrapper.get("[data-testid='ov-stat-discovery']").text()).toContain("1");
    expect(wrapper.get("[data-testid='ov-stat-sessions']").text()).toContain("2");
    expect(wrapper.get("[data-testid='ov-stat-sources']").text()).toContain("2");
    expect(wrapper.get("[data-testid='ov-stat-quota']").text()).toContain("3 / 60");
    expect(wrapper.findAll("[data-testid='ov-case-row']")).toHaveLength(3);
    expect(wrapper.findAll("[data-bucket='2026-11-09']")).toHaveLength(1);
  });

  it("writes range, grain, and source filters into the URL and resets the page", async () => {
    mockOverviewApi();
    const { router, wrapper } = await mountPage(`${ws}/overview?page=2`);

    await wrapper.get("[data-testid='ov-range-30']").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query.range).toBe("30");
    expect(router.currentRoute.value.query.page).toBeUndefined();

    await wrapper.get("[data-testid='ov-grain-day']").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query.grain).toBe("day");

    await wrapper.get("[data-testid='ov-source-option-workflow']").setValue(true);
    await flushPromises();
    expect(router.currentRoute.value.query.objects).toBe("workflow");
    expect(wrapper.find("[data-testid='ov-chip-workflow']").exists()).toBe(true);

    await wrapper.get("[data-testid='ov-stat-self']").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query.type).toBe("self");
    expect(wrapper.find("[data-testid='ov-type-chip']").exists()).toBe(true);

    await wrapper.get("[data-testid='ov-type-clear']").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query.type).toBeUndefined();
  });

  it("restores filters from a deep link and sends them to every request", async () => {
    mockOverviewApi();
    const { router, wrapper } = await mountPage(
      `${ws}/overview?tab=cases&range=30&grain=day&objects=deep-research,workflow&page=2&type=self`,
    );

    expect(decodeURIComponent(router.currentRoute.value.fullPath)).toContain(
      "objects=deep-research,workflow",
    );

    const summaryUrl = new URL(requests.summary.at(-1) as string);
    expect(summaryUrl.searchParams.get("range")).toBe("30");
    expect(summaryUrl.searchParams.get("objects")).toBe("deep-research,workflow");

    const trendUrl = new URL(requests.trend.at(-1) as string);
    expect(trendUrl.searchParams.get("grain")).toBe("day");

    const casesUrl = new URL(requests.cases.at(-1) as string);
    expect(casesUrl.searchParams.get("page")).toBe("2");
    expect(casesUrl.searchParams.get("pageSize")).toBe("8");
    expect(casesUrl.searchParams.get("badCaseType")).toBe("self");

    expect(wrapper.find("[data-testid='ov-chip-deep-research']").exists()).toBe(true);
  });

  it("removes one chip and clears every filter back to the defaults", async () => {
    mockOverviewApi();
    const { router, wrapper } = await mountPage(
      `${ws}/overview?range=custom&from=2026-10-01&to=2026-10-31&objects=deep-research,workflow&type=discovery`,
    );

    await wrapper
      .get("[data-testid='ov-chip-deep-research'] button")
      .trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query.objects).toBe("workflow");

    await wrapper.get("[data-testid='ov-clear']").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query).toEqual({
      tab: "cases",
      range: "90",
      grain: "week",
    });
    expect(requests.cases.at(-1)).toContain("range=90");
  });

  it("turns a clicked bucket into the list's custom window", async () => {
    mockOverviewApi();
    const { router, wrapper } = await mountPage();

    await wrapper.get("[data-bucket='2026-11-02']").trigger("click");
    await flushPromises();

    expect(router.currentRoute.value.query).toEqual({
      tab: "cases",
      range: "custom",
      grain: "week",
      from: "2026-11-02",
      to: "2026-11-08",
    });
    const casesUrl = new URL(requests.cases.at(-1) as string);
    expect(casesUrl.searchParams.get("from")).toBe("2026-11-02");
    expect(casesUrl.searchParams.get("to")).toBe("2026-11-08");
    expect(casesUrl.searchParams.has("range")).toBe(false);
  });

  it("guards the M11 targets tab by redirecting to the cases tab", async () => {
    mockOverviewApi();
    const { router, wrapper } = await mountPage(`${ws}/overview?tab=targets`);

    expect(router.currentRoute.value.query.tab).toBe("cases");
    expect(wrapper.find("[data-testid='ov-targets-notice']").exists()).toBe(true);
    expect(
      wrapper.get("[data-testid='ov-tab-targets']").attributes("disabled"),
    ).toBeDefined();
    expect(wrapper.get("[data-testid='ov-tab-cases']").classes()).toContain(
      "active",
    );
  });

  it("keeps the chart alive when the list fails", async () => {
    mockOverviewApi();
    server.use(
      http.get("/api/workspaces/:wid/bad-cases", () =>
        HttpResponse.json(
          { error: { code: "INTERNAL", message: "boom", details: {} } },
          { status: 500 },
        ),
      ),
    );
    const { wrapper } = await mountPage();

    expect(wrapper.find("[data-testid='ov-case-error']").exists()).toBe(true);
    expect(wrapper.findAll("[data-bucket]").length).toBe(2);
    expect(wrapper.get("[data-testid='ov-stat-badcases']").text()).toContain("3");
  });

  it("keeps the list alive when the chart fails", async () => {
    mockOverviewApi();
    server.use(
      http.get("/api/workspaces/:wid/overview/trend", () =>
        HttpResponse.json(
          { error: { code: "INTERNAL", message: "boom", details: {} } },
          { status: 500 },
        ),
      ),
    );
    const { wrapper } = await mountPage();

    expect(wrapper.find("[data-testid='ov-chart-error']").exists()).toBe(true);
    expect(wrapper.findAll("[data-testid='ov-case-row']")).toHaveLength(3);
    expect(wrapper.get("[data-testid='ov-stat-badcases']").text()).toContain("3");
  });

  it("shows the empty workspace copy only when nothing matches", async () => {
    mockOverviewApi({
      summary: {
        window: { from: "2026-08-19", to: "2026-11-16" },
        totals: {
          badCases: 0,
          self: 0,
          discovery: 0,
          sessions: 0,
          sources: 0,
          quota: 60,
          used: 0,
        },
        objects: [],
      },
      trend: {
        window: { from: "2026-08-19", to: "2026-11-16" },
        grain: "week",
        buckets: [],
      },
      sources: { items: [] },
      cases: { items: [], total: 0, page: 1, pageSize: 8 },
    });
    const { wrapper } = await mountPage();

    expect(wrapper.find("[data-testid='ov-chart-empty']").exists()).toBe(true);
    expect(wrapper.get("[data-testid='ov-case-empty']").text()).toContain(
      "这个空间还没有 bad case",
    );
  });

  it("resets foreign filters when the workspace changes", async () => {
    mockOverviewApi();
    const { router } = await mountPage(
      `${ws}/overview?range=7&objects=deep-research`,
      [testWorkspace(), testWorkspace({ id: "ws-other", name: "其他空间" })],
    );

    expect(router.currentRoute.value.query.range).toBe("7");

    await router.push(
      "/workspaces/ws-other/overview?range=7&objects=deep-research",
    );
    await flushPromises();

    expect(router.currentRoute.value.path).toBe("/workspaces/ws-other/overview");
    await vi.waitFor(() => {
      expect(router.currentRoute.value.query).toEqual({
        tab: "cases",
        range: "90",
        grain: "week",
      });
    });
  });
});
