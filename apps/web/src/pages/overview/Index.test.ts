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

import LaunchWizard from "../evolution/components/LaunchWizard.vue";
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
    syncStatus: "ready",
    sessionReady: true,
    lastError: null,
    retryable: false,
    nextRetryAt: null,
  };
}

const cases = {
  items: [caseRow(1), caseRow(2), caseRow(3)],
  total: 3,
  page: 1,
  pageSize: 8,
};

const targetItems = [
  {
    targetId: "target-1",
    objectType: "skill",
    objectName: "synthetic-review",
    versions: ["v2", "main"],
    sessions: 3,
    potential: 3,
    attributed: 1,
    nonTarget: 1,
    unanalyzed: 1,
    evolvable: 2,
  },
  {
    targetId: "target-2",
    objectType: "agent",
    objectName: "review-agent",
    versions: ["2026.11.2"],
    sessions: 2,
    potential: 1,
    attributed: 1,
    nonTarget: 0,
    unanalyzed: 0,
    evolvable: 1,
  },
];

const targetSummary = {
  targets: 2,
  sessions: 5,
  potential: 4,
  attributed: 2,
  nonTarget: 1,
  unanalyzed: 1,
};

const targetOverview = {
  summary: targetSummary,
  items: targetItems,
  total: 2,
  page: 1,
  pageSize: 50,
};

const targetTrend = {
  window: { from: "2026-08-19", to: "2026-11-16" },
  grain: "week",
  buckets: [
    {
      bucket: "2026-11-09",
      label: "11-09",
      attributed: 1,
      nonTarget: 1,
      unanalyzed: 1,
      byTarget: [
        {
          targetId: "target-1",
          objectType: "skill",
          objectName: "synthetic-review",
          attributed: 1,
          nonTarget: 1,
          unanalyzed: 1,
        },
        {
          targetId: "target-2",
          objectType: "agent",
          objectName: "review-agent",
          attributed: 0,
          nonTarget: 0,
          unanalyzed: 0,
        },
      ],
    },
  ],
  meta: { bucketPolicy: "attributed and nonTarget rows bucket by attribution createdAt; unanalyzed rows bucket by badCase createdAt" },
};

const targetDetail = {
  target: {
    targetId: "target-1",
    objectType: "skill",
    objectName: "synthetic-review",
    defaultRef: "main",
    versions: ["v2", "main"],
  },
  stats: { sessions: 3, potential: 3, distinctCases: 2, versions: 2 },
  byVersion: [
    {
      version: "v2",
      potential: 2,
      attributed: 1,
      nonTarget: 1,
      unanalyzed: 0,
    },
    {
      version: "main",
      potential: 1,
      attributed: 0,
      nonTarget: 0,
      unanalyzed: 1,
    },
  ],
  bySource: [{ source: "Explore", total: 2, distinctCases: 2 }],
};

const targetCases = {
  items: [
    {
      badCaseId: "badcase-synthetic-0001",
      objectType: "skill",
      objectName: "synthetic-review",
      objectVersion: "v2",
      source: "Explore",
      state: "attributed",
      badCaseType: "self",
      title: "检查结论缺少目标文件",
      createdAt: "2026-10-20T09:03:00+08:00",
      sessionId: "10000000-0000-4000-8000-000000000001",
      attributionId: "probe-synthetic-0002",
      category: "prompt",
    },
  ],
  total: 1,
  page: 1,
  pageSize: 8,
};

const evolutionTargets = { items: [] };

type RequestLog = {
  summary: string[];
  trend: string[];
  sources: string[];
  cases: string[];
  targets: string[];
  targetTrend: string[];
  targetCases: string[];
  targetDetail: string[];
  evolutionTargets: string[];
};

let requests: RequestLog;
const mounted: VueWrapper[] = [];

function apiError(status: number, code: string, message = "boom") {
  return HttpResponse.json(
    { error: { code, message, details: {} } },
    { status },
  );
}

function requestPaths(log: string[], wid: string): URL[] {
  return log
    .filter((url) => new URL(url).pathname.startsWith(`/api/workspaces/${wid}/`))
    .map((url) => new URL(url));
}

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
    http.get("/api/workspaces/:wid/overview/targets", ({ request }) => {
      requests.targets.push(request.url);
      return HttpResponse.json(overrides.targets ?? targetOverview);
    }),
    http.get("/api/workspaces/:wid/overview/targets/trend", ({ request }) => {
      requests.targetTrend.push(request.url);
      return HttpResponse.json(overrides.targetTrend ?? targetTrend);
    }),
    http.get("/api/workspaces/:wid/overview/targets/cases", ({ request }) => {
      requests.targetCases.push(request.url);
      return HttpResponse.json(overrides.targetCases ?? targetCases);
    }),
    http.get(
      "/api/workspaces/:wid/overview/targets/:targetId/detail",
      ({ request }) => {
        requests.targetDetail.push(request.url);
        return HttpResponse.json(overrides.targetDetail ?? targetDetail);
      },
    ),
    http.get("/api/workspaces/:wid/evolution/targets", ({ request }) => {
      requests.evolutionTargets.push(request.url);
      return HttpResponse.json(overrides.evolutionTargets ?? evolutionTargets);
    }),
    http.get("/api/workspaces/:wid/catalogs/targets", () =>
      HttpResponse.json(overrides.catalogs ?? { skill: [], agent: [] }),
    ),
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
    requests = {
      summary: [],
      trend: [],
      sources: [],
      cases: [],
      targets: [],
      targetTrend: [],
      targetCases: [],
      targetDetail: [],
      evolutionTargets: [],
    };
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

  it("shows both workflow actions and the operational context to an administrator", async () => {
    mockOverviewApi();
    const { wrapper } = await mountPage();

    expect(wrapper.find("[data-testid='ov-readonly-actions']").exists()).toBe(
      false,
    );
    expect(
      wrapper.get("[data-testid='ov-action-ingest']").attributes("href"),
    ).toBe(`${ws}/admin?tab=ingest`);
    expect(wrapper.find("[data-testid='ov-action-launch']").exists()).toBe(true);

    const context = wrapper.get("[data-testid='ov-context']");
    expect(context.text()).toContain("空间额度");
    expect(context.text()).toContain("上报接入");
    expect(context.text()).toContain("当前空间");
    expect(
      wrapper.get("[data-testid='ov-context-quota-used']").text(),
    ).toBe("3 / 60");
    expect(
      wrapper.get("[data-testid='ov-context-quota-percent']").text(),
    ).toBe("5% 已使用");
    expect(
      wrapper.get("[data-testid='ov-context-quota-remaining']").text(),
    ).toBe("剩余 57");
    expect(
      wrapper.get("[data-testid='ov-context-endpoint']").text(),
    ).toContain(`${window.location.origin}/api/workspaces/${workspaceId}/bad-cases`);
    expect(
      wrapper.get("[data-testid='ov-context-admin-count']").text(),
    ).toBe("1 人");
    expect(
      wrapper.get("[data-testid='ov-context-member-count']").text(),
    ).toBe("3 人");
    expect(wrapper.get("[data-testid='ov-context-role']").text()).toBe(
      "全局管理员",
    );
    expect(wrapper.get("[data-testid='ov-context-sources']").text()).toBe(
      "2 个",
    );
  });

  it("copies the derived ingest endpoint without exposing a credential", async () => {
    const writes: string[] = [];
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: async (value: string) => writes.push(value) },
    });
    mockOverviewApi();
    const { wrapper } = await mountPage();

    await wrapper.get("[data-testid='ov-context-copy']").trigger("click");
    await flushPromises();

    expect(writes).toEqual([
      `${window.location.origin}/api/workspaces/${workspaceId}/bad-cases`,
    ]);
    expect(wrapper.get("[data-testid='ov-context-copy']").text()).toBe("已复制");
  });

  it("hides write actions from a read-only member while keeping the context", async () => {
    mockOverviewApi();
    const { wrapper } = await mountPage(`${ws}/overview`, [
      testWorkspace({ role: "viewer" }),
    ]);

    expect(wrapper.find("[data-testid='ov-action-ingest']").exists()).toBe(false);
    expect(wrapper.find("[data-testid='ov-action-launch']").exists()).toBe(false);
    expect(wrapper.get("[data-testid='ov-readonly-actions']").text()).toContain(
      "只读访问",
    );
    expect(wrapper.find("[data-testid='ov-context']").exists()).toBe(true);
    expect(wrapper.get("[data-testid='ov-context-role']").text()).toBe(
      "只读成员",
    );
    expect(
      wrapper.find("[data-testid='ov-context-ingest-link']").exists(),
    ).toBe(false);
    expect(wrapper.findAll("[data-testid='ov-case-row']")).toHaveLength(3);
  });

  it("keeps write actions for a space administrator but not for a plain member", async () => {
    mockOverviewApi();
    const spaceAdmin = await mountPage(`${ws}/overview`, [
      testWorkspace({ role: "space_admin" }),
    ]);
    expect(
      spaceAdmin.wrapper.find("[data-testid='ov-action-ingest']").exists(),
    ).toBe(true);
    expect(
      spaceAdmin.wrapper.find("[data-testid='ov-action-launch']").exists(),
    ).toBe(true);
    expect(
      spaceAdmin.wrapper.get("[data-testid='ov-context-role']").text(),
    ).toBe("空间管理员");

    const member = await mountPage(`${ws}/overview`, [
      testWorkspace({ role: "member" }),
    ]);
    expect(member.wrapper.find("[data-testid='ov-action-ingest']").exists()).toBe(
      false,
    );
    expect(member.wrapper.find("[data-testid='ov-action-launch']").exists()).toBe(
      false,
    );
    expect(
      member.wrapper.get("[data-testid='ov-readonly-actions']").text(),
    ).toContain("只读访问");
    expect(member.wrapper.get("[data-testid='ov-context-role']").text()).toBe(
      "成员",
    );
  });

  it("opens the existing launch wizard from the overview", async () => {
    mockOverviewApi();
    const { wrapper } = await mountPage();

    await wrapper.get("[data-testid='ov-action-launch']").trigger("click");
    await vi.waitFor(() => {
      expect(wrapper.find("[data-testid='launch-wizard']").exists()).toBe(true);
    });

    await wrapper.get("[aria-label='关闭向导']").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-testid='launch-wizard']").exists()).toBe(false);
  });

  it("pushes the accepted run detail after the wizard launches", async () => {
    mockOverviewApi();
    const { router, wrapper } = await mountPage();
    const push = vi
      .spyOn(router, "push")
      .mockImplementation(async () => undefined);

    await wrapper.get("[data-testid='ov-action-launch']").trigger("click");
    await vi.waitFor(() => {
      expect(wrapper.findComponent(LaunchWizard).exists()).toBe(true);
    });
    wrapper.findComponent(LaunchWizard).vm.$emit("launched", "full", "run-1");
    await flushPromises();
    expect(wrapper.find("[data-testid='launch-wizard']").exists()).toBe(false);
    expect(push).toHaveBeenCalledWith(
      `/workspaces/${workspaceId}/evolution/runs/run-1`,
    );

    await wrapper.get("[data-testid='ov-action-launch']").trigger("click");
    await vi.waitFor(() => {
      expect(wrapper.findComponent(LaunchWizard).exists()).toBe(true);
    });
    wrapper
      .findComponent(LaunchWizard)
      .vm.$emit("launched", "cluster_only", "run-2");
    await flushPromises();
    expect(push).toHaveBeenCalledWith(
      `/workspaces/${workspaceId}/evolution/cluster/run-2`,
    );
  });

  it("writes global range, grain, and source filters without touching the list page", async () => {
    mockOverviewApi({
      cases: { items: [caseRow(1)], total: 17, page: 2, pageSize: 8 },
    });
    const { router, wrapper } = await mountPage(`${ws}/overview?page=2`);

    await wrapper.get("[data-testid='ov-range-30']").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query.range).toBe("30");
    expect(router.currentRoute.value.query.page).toBe("2");

    await wrapper.get("[data-testid='ov-grain-day']").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query.grain).toBe("day");

    await wrapper.get("[data-testid='ov-source-option-workflow']").setValue(true);
    await flushPromises();
    expect(router.currentRoute.value.query.objects).toBe("workflow");
    expect(router.currentRoute.value.query.page).toBe("2");
    expect(wrapper.find("[data-testid='ov-chip-workflow']").exists()).toBe(true);

    await wrapper.get("[data-testid='ov-stat-self']").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query.type).toBe("self");
    expect(router.currentRoute.value.query.page).toBeUndefined();
    expect(
      (wrapper.get("[data-testid='ov-list-type']").element as HTMLSelectElement)
        .value,
    ).toBe("self");

    await wrapper.get("[data-testid='ov-list-type']").setValue("all");
    await flushPromises();
    expect(router.currentRoute.value.query.type).toBeUndefined();
  });

  it("defaults quick ranges to day for 7 days and week for 30/90", async () => {
    mockOverviewApi();
    const { router, wrapper } = await mountPage(`${ws}/overview?range=90&grain=week`);

    await wrapper.get("[data-testid='ov-range-7']").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query).toMatchObject({
      range: "7",
      grain: "day",
    });
    expect(
      new URL(requests.trend.at(-1) as string).searchParams.get("grain"),
    ).toBe("day");

    await wrapper.get("[data-testid='ov-range-30']").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query).toMatchObject({
      range: "30",
      grain: "week",
    });

    await wrapper.get("[data-testid='ov-grain-month']").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query.grain).toBe("month");

    await wrapper.get("[data-testid='ov-range-90']").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query).toMatchObject({
      range: "90",
      grain: "week",
    });
  });

  it("restores filters from a deep link and sends them to every request", async () => {
    mockOverviewApi({
      cases: { items: [caseRow(1)], total: 17, page: 2, pageSize: 8 },
    });
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
    // The list's empty date/source filters stay independent of the chart's
    // range=30 and objects=deep-research,workflow.
    expect(casesUrl.searchParams.get("allTime")).toBe("true");
    expect(casesUrl.searchParams.has("from")).toBe(false);
    expect(casesUrl.searchParams.has("objects")).toBe(false);

    expect(wrapper.find("[data-testid='ov-chip-deep-research']").exists()).toBe(true);
  });

  it("removes one chip, clears only global filters, then resets the list", async () => {
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
      type: "discovery",
    });
    expect(requests.cases.at(-1)).toContain("allTime=true");
    expect(requests.cases.at(-1)).toContain("badCaseType=discovery");

    await wrapper.get("[data-testid='ov-list-reset']").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query).toEqual({
      tab: "cases",
      range: "90",
      grain: "week",
    });
  });

  it("turns a clicked bucket into the list's own window", async () => {
    mockOverviewApi();
    const { router, wrapper } = await mountPage();

    await wrapper.get("[data-bucket='2026-11-02']").trigger("click");
    await flushPromises();

    // The chart keeps its 90-day window; only the list narrows to the bucket.
    expect(router.currentRoute.value.query).toEqual({
      tab: "cases",
      range: "90",
      grain: "week",
      lfrom: "2026-11-02",
      lto: "2026-11-08",
    });
    const casesUrl = new URL(requests.cases.at(-1) as string);
    expect(casesUrl.searchParams.get("lfrom")).toBeNull();
    expect(casesUrl.searchParams.get("from")).toBe("2026-11-02");
    expect(casesUrl.searchParams.get("to")).toBe("2026-11-08");
    expect(casesUrl.searchParams.has("allTime")).toBe(false);
    expect(casesUrl.searchParams.has("range")).toBe(false);
  });

  it("applies the list's own source and type filters without touching the chart", async () => {
    mockOverviewApi({
      cases: { items: [caseRow(1)], total: 17, page: 1, pageSize: 8 },
    });
    const { router, wrapper } = await mountPage(
      `${ws}/overview?range=7&objects=deep-research`,
    );

    await wrapper.get("[data-testid='ov-list-object']").setValue("workflow");
    await flushPromises();
    expect(router.currentRoute.value.query.lobject).toBe("workflow");
    expect(router.currentRoute.value.query.range).toBe("7");
    expect(router.currentRoute.value.query.objects).toBe("deep-research");
    let url = new URL(requests.cases.at(-1) as string);
    expect(url.searchParams.get("objects")).toBe("workflow");
    expect(url.searchParams.get("allTime")).toBe("true");
    expect(url.searchParams.has("from")).toBe(false);

    await wrapper.get("[data-testid='ov-list-type']").setValue("self");
    await flushPromises();
    expect(router.currentRoute.value.query.type).toBe("self");
    url = new URL(requests.cases.at(-1) as string);
    expect(url.searchParams.get("badCaseType")).toBe("self");

    await wrapper.get("[data-testid='ov-list-reset']").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query).toEqual({
      tab: "cases",
      range: "7",
      grain: "day",
      objects: "deep-research",
    });
  });

  it("keeps an incomplete list date pair out of the query and restores all time", async () => {
    mockOverviewApi();
    const { router, wrapper } = await mountPage();
    const before = requests.cases.length;

    await wrapper.get("[data-testid='ov-list-from']").setValue("2026-10-01");
    await flushPromises();
    expect(requests.cases.length).toBe(before);
    expect(router.currentRoute.value.query.lfrom).toBeUndefined();
    expect(wrapper.get("[data-testid='ov-list-date-error']").text()).toContain(
      "请同时选择",
    );

    await wrapper.get("[data-testid='ov-list-to']").setValue("2026-10-31");
    await flushPromises();
    expect(router.currentRoute.value.query.lfrom).toBe("2026-10-01");
    expect(router.currentRoute.value.query.lto).toBe("2026-10-31");
    let url = new URL(requests.cases.at(-1) as string);
    expect(url.searchParams.get("from")).toBe("2026-10-01");
    expect(url.searchParams.get("to")).toBe("2026-10-31");
    expect(url.searchParams.has("allTime")).toBe(false);

    await wrapper.get("[data-testid='ov-list-from']").setValue("");
    await flushPromises();
    expect(wrapper.get("[data-testid='ov-list-date-error']").text()).toContain(
      "请同时选择",
    );
    await wrapper.get("[data-testid='ov-list-to']").setValue("");
    await flushPromises();
    expect(router.currentRoute.value.query.lfrom).toBeUndefined();
    expect(router.currentRoute.value.query.lto).toBeUndefined();
    url = new URL(requests.cases.at(-1) as string);
    expect(url.searchParams.get("allTime")).toBe("true");
    expect(url.searchParams.has("from")).toBe(false);
  });

  it("restores list filters and paging from a deep link", async () => {
    mockOverviewApi({
      cases: { items: [caseRow(1)], total: 17, page: 2, pageSize: 8 },
    });
    const { wrapper } = await mountPage(
      `${ws}/overview?lfrom=2026-10-01&lto=2026-10-31&lobject=deep-research&type=self&page=2`,
    );

    const from = wrapper.get("[data-testid='ov-list-from']")
      .element as HTMLInputElement;
    const to = wrapper.get("[data-testid='ov-list-to']")
      .element as HTMLInputElement;
    expect(from.value).toBe("2026-10-01");
    expect(to.value).toBe("2026-10-31");
    expect(
      (wrapper.get("[data-testid='ov-list-object']").element as HTMLSelectElement)
        .value,
    ).toBe("deep-research");
    expect(
      (wrapper.get("[data-testid='ov-list-type']").element as HTMLSelectElement)
        .value,
    ).toBe("self");

    const url = new URL(requests.cases.at(-1) as string);
    expect(url.searchParams.get("from")).toBe("2026-10-01");
    expect(url.searchParams.get("to")).toBe("2026-10-31");
    expect(url.searchParams.get("objects")).toBe("deep-research");
    expect(url.searchParams.get("badCaseType")).toBe("self");
    expect(url.searchParams.get("page")).toBe("2");
  });

  it("opens the evolution-target view from a deep link", async () => {
    mockOverviewApi();
    const { router, wrapper } = await mountPage(`${ws}/overview?tab=targets`);

    expect(router.currentRoute.value.query.tab).toBe("targets");
    expect(wrapper.get("[data-testid='ov-tab-targets']").classes()).toContain(
      "active",
    );
    expect(wrapper.get("[data-testid='ov-target-stat-targets']").text()).toBe(
      "2",
    );
    expect(wrapper.get("[data-testid='ov-target-stat-sessions']").text()).toBe(
      "5",
    );
    expect(wrapper.get("[data-testid='ov-target-stat-attributed']").text()).toBe(
      "2",
    );
    expect(wrapper.findAll("[data-testid='ov-target-side-item-target-1']")).toHaveLength(1);
    expect(wrapper.findAll("[data-testid='ov-target-side-item-target-2']")).toHaveLength(1);
    expect(wrapper.findAll("[data-testid='ov-target-case-row']")).toHaveLength(1);
    expect(wrapper.get("[data-testid='ov-target-detail-sessions']").text()).toBe(
      "3",
    );
    expect(wrapper.find("[data-testid='ov-target-chart']").exists()).toBe(true);

    const casesUrl = new URL(requests.targetCases.at(-1) as string);
    expect(casesUrl.searchParams.get("pageSize")).toBe("8");
    const targetsUrl = new URL(requests.targets.at(-1) as string);
    expect(targetsUrl.searchParams.get("pageSize")).toBe("50");
  });

  it("opens the existing launch wizard from the target overview header", async () => {
    mockOverviewApi();
    const { router, wrapper } = await mountPage(
      `${ws}/overview?tab=targets&range=30&grain=day`,
    );

    expect(wrapper.find("[data-testid='ov-target-create']").exists()).toBe(true);
    const launch = wrapper.get("[data-testid='ov-target-launch']");
    expect(launch.text()).toBe("启动自进化");
    expect(launch.classes()).toContain("primary");

    await launch.trigger("click");
    await vi.waitFor(() => {
      expect(wrapper.find("[data-testid='launch-wizard']").exists()).toBe(true);
      expect(
        wrapper.find("[data-testid='wizard-config-empty']").exists(),
      ).toBe(true);
    });

    await wrapper.get("[aria-label='关闭向导']").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-testid='launch-wizard']").exists()).toBe(false);
    expect(router.currentRoute.value.query).toMatchObject({
      tab: "targets",
      range: "30",
      grain: "day",
    });

    await wrapper.get("[data-testid='ov-target-launch']").trigger("click");
    await vi.waitFor(() => {
      expect(
        wrapper.find("[data-testid='wizard-target-config-link']").exists(),
      ).toBe(true);
    });
    await wrapper.get("[data-testid='wizard-target-config-link']").trigger("click");
    await vi.waitFor(() => {
      expect(router.currentRoute.value.path).toBe(`${ws}/evolution/targets`);
    });
  });

  it("gates the target header actions with the same management role", async () => {
    mockOverviewApi();
    const spaceAdmin = await mountPage(`${ws}/overview?tab=targets`, [
      testWorkspace({ role: "space_admin" }),
    ]);
    expect(
      spaceAdmin.wrapper.find("[data-testid='ov-target-create']").exists(),
    ).toBe(true);
    expect(
      spaceAdmin.wrapper.find("[data-testid='ov-target-launch']").exists(),
    ).toBe(true);

    for (const role of ["member", "viewer"] as const) {
      mockOverviewApi();
      const readOnly = await mountPage(`${ws}/overview?tab=targets`, [
        testWorkspace({ role }),
      ]);
      expect(
        readOnly.wrapper.find("[data-testid='ov-target-create']").exists(),
      ).toBe(false);
      expect(
        readOnly.wrapper.find("[data-testid='ov-target-launch']").exists(),
      ).toBe(false);
      expect(readOnly.wrapper.get(".head-actions").text()).toContain("只读访问");
      expect(
        readOnly.wrapper.get("[data-testid='ov-target-stat-targets']").text(),
      ).toBe("2");
    }
  });

  it("shows a retryable target load error instead of a false empty state", async () => {
    mockOverviewApi();
    server.use(
      http.get("/api/workspaces/:wid/overview/targets", () =>
        apiError(500, "INTERNAL", "target aggregation failed"),
      ),
    );
    const { wrapper } = await mountPage(`${ws}/overview?tab=targets`);

    expect(wrapper.find("[data-testid='ov-target-load-error']").exists()).toBe(
      true,
    );
    expect(wrapper.get("[data-testid='ov-target-load-error']").text()).toContain(
      "INTERNAL",
    );
    expect(wrapper.find("[data-testid='ov-target-side-error']").exists()).toBe(
      true,
    );
  });

  it("keeps the shared window and grain when switching overview tabs", async () => {
    mockOverviewApi();
    const { router, wrapper } = await mountPage(
      `${ws}/overview?tab=cases&range=30&grain=day`,
    );

    await wrapper.get("[data-testid='ov-tab-targets']").trigger("click");
    await flushPromises();

    expect(router.currentRoute.value.query).toMatchObject({
      tab: "targets",
      range: "30",
      grain: "day",
    });
    const trendUrl = new URL(requests.targetTrend.at(-1) as string);
    expect(trendUrl.searchParams.get("range")).toBe("30");
    expect(trendUrl.searchParams.get("grain")).toBe("day");

    await wrapper.get("[data-testid='ov-tab-cases']").trigger("click");
    await flushPromises();

    expect(router.currentRoute.value.query).toEqual({
      tab: "cases",
      range: "30",
      grain: "day",
    });
  });

  it("writes target, state, detail, and list filters into the target URL", async () => {
    mockOverviewApi();
    const { router, wrapper } = await mountPage(`${ws}/overview?tab=targets`);

    await wrapper.get("[data-testid='ov-target-option-target-2']").setValue(true);
    await flushPromises();
    expect(router.currentRoute.value.query.targets).toBe("target-2");
    expect(wrapper.find("[data-testid='ov-target-chip-target-2']").exists()).toBe(true);

    await wrapper.get("[data-testid='ov-target-metric-unanalyzed']").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query.states).toBe("attributed,nonTarget");

    await wrapper.get("[data-testid='ov-target-case-target']").setValue("target-1");
    await flushPromises();
    expect(router.currentRoute.value.query.ctarget).toBe("target-1");
    const casesUrl = new URL(requests.targetCases.at(-1) as string);
    expect(casesUrl.searchParams.get("targets")).toBe("target-1");

    await wrapper.get("[data-testid='ov-target-case-state']").setValue("nonTarget");
    await flushPromises();
    expect(router.currentRoute.value.query.cstate).toBe("nonTarget");
    const filteredUrl = new URL(requests.targetCases.at(-1) as string);
    expect(filteredUrl.searchParams.get("states")).toBe("nonTarget");

    await wrapper.get("[data-testid='ov-target-detail-target']").setValue("target-2");
    await flushPromises();
    expect(router.currentRoute.value.query.dtarget).toBe("target-2");

    await wrapper.get("[data-testid='ov-target-detail-limit-all']").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query.dlimit).toBe("all");

    await wrapper.get("[data-testid='ov-target-detail-from']").setValue("2026-11-01");
    await flushPromises();
    await wrapper.get("[data-testid='ov-target-detail-to']").setValue("2026-11-10");
    await flushPromises();
    expect(router.currentRoute.value.query.dfrom).toBe("2026-11-01");
    expect(router.currentRoute.value.query.dto).toBe("2026-11-10");
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
    expect(
      wrapper.get("[data-testid='ov-context-quota-used']").text(),
    ).toBe("0 / 60");
    expect(wrapper.get("[data-testid='ov-context-sources']").text()).toBe(
      "0 个",
    );
    expect(wrapper.find("[data-testid='ov-source-matrix']").exists()).toBe(
      false,
    );
  });

  it("requests the new workspace with default filters before anything else", async () => {
    mockOverviewApi();
    const { router } = await mountPage(
      `${ws}/overview?range=7&objects=deep-research&type=self`,
      [testWorkspace(), testWorkspace({ id: "ws-other", name: "其他空间" })],
    );

    expect(router.currentRoute.value.query.range).toBe("7");

    // The workspace picker navigates with the canonical default query, so the
    // page never renders the new workspace under the previous filters.
    await router.push(
      "/workspaces/ws-other/overview?tab=cases&range=90&grain=week",
    );
    await flushPromises();

    expect(router.currentRoute.value.path).toBe("/workspaces/ws-other/overview");
    await vi.waitFor(() => {
      expect(requests.summary.some((url) => url.includes("/ws-other/"))).toBe(
        true,
      );
    });

    const summaryForeign = [
      ...requestPaths(requests.summary, "ws-other"),
      ...requestPaths(requests.trend, "ws-other"),
      ...requestPaths(requests.sources, "ws-other"),
    ];
    expect(summaryForeign.length).toBeGreaterThan(0);
    for (const url of summaryForeign) {
      expect(url.searchParams.get("range")).toBe("90");
      expect(url.searchParams.has("objects")).toBe(false);
      expect(url.searchParams.has("badCaseType")).toBe(false);
    }
    const caseForeign = requestPaths(requests.cases, "ws-other");
    expect(caseForeign.length).toBeGreaterThan(0);
    for (const url of caseForeign) {
      expect(url.searchParams.get("allTime")).toBe("true");
      expect(url.searchParams.has("range")).toBe(false);
      expect(url.searchParams.has("objects")).toBe(false);
      expect(url.searchParams.has("badCaseType")).toBe(false);
    }
  });

  it("restores the previous workspace filters on browser back", async () => {
    mockOverviewApi();
    const { router } = await mountPage(
      `${ws}/overview?range=7&objects=deep-research`,
      [testWorkspace(), testWorkspace({ id: "ws-other", name: "其他空间" })],
    );

    await router.push(
      "/workspaces/ws-other/overview?tab=cases&range=90&grain=week",
    );
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/workspaces/ws-other/overview");

    router.back();
    await vi.waitFor(() => {
      expect(router.currentRoute.value.path).toBe(`${ws}/overview`);
      expect(router.currentRoute.value.query).toEqual({
        tab: "cases",
        range: "7",
        grain: "day",
        objects: "deep-research",
      });
    });
    await vi.waitFor(() => {
      const summaryUrls = requestPaths(requests.summary, workspaceId);
      expect(
        summaryUrls.some(
          (url) =>
            url.searchParams.get("range") === "7" &&
            url.searchParams.get("objects") === "deep-research",
        ),
      ).toBe(true);
      const caseUrls = requestPaths(requests.cases, workspaceId);
      expect(
        caseUrls.some((url) => url.searchParams.get("allTime") === "true"),
      ).toBe(true);
    });
  });

  it("uses the effective week grain when a day request is downgraded", async () => {
    mockOverviewApi({
      trend: {
        window: { from: "2026-08-01", to: "2026-11-16" },
        grain: "week",
        buckets: [
          {
            bucket: "2026-08-17",
            label: "08-17",
            self: 2,
            discovery: 1,
            total: 3,
          },
        ],
      },
    });
    const { router, wrapper } = await mountPage(
      `${ws}/overview?range=custom&from=2026-08-01&to=2026-11-16&grain=day`,
    );

    expect(wrapper.get("[data-testid='ov-grain-downgraded']").text()).toBe(
      "已按周展示",
    );
    expect(wrapper.get("[data-testid='ov-chart-card'] .hint").text()).toContain(
      "按周聚合",
    );

    await wrapper.get("[data-bucket='2026-08-17']").trigger("click");
    await flushPromises();

    expect(router.currentRoute.value.query).toEqual({
      tab: "cases",
      range: "custom",
      grain: "day",
      from: "2026-08-01",
      to: "2026-11-16",
      lfrom: "2026-08-17",
      lto: "2026-08-23",
    });
    const casesUrl = new URL(requests.cases.at(-1) as string);
    expect(casesUrl.searchParams.get("from")).toBe("2026-08-17");
    expect(casesUrl.searchParams.get("to")).toBe("2026-08-23");
    expect(casesUrl.searchParams.has("allTime")).toBe(false);
  });

  it("clamps an out-of-range page to the last valid page", async () => {
    mockOverviewApi();
    server.use(
      http.get("/api/workspaces/:wid/bad-cases", ({ request }) => {
        requests.cases.push(request.url);
        const page = Number(
          new URL(request.url).searchParams.get("page") ?? "1",
        );
        return HttpResponse.json({
          items:
            page === 1
              ? [caseRow(1), caseRow(2), caseRow(3)]
              : page === 3
                ? [caseRow(3)]
                : [],
          total: 17,
          page,
          pageSize: 8,
        });
      }),
    );

    const { router, wrapper } = await mountPage(`${ws}/overview?page=99`);

    await vi.waitFor(() => {
      expect(router.currentRoute.value.query.page).toBe("3");
      expect(wrapper.findAll("[data-testid='ov-case-row']")).toHaveLength(1);
    });
    expect(
      wrapper.find("[data-testid='ov-case-page-out-of-range']").exists(),
    ).toBe(false);
    expect(wrapper.get("[data-testid='ov-pager']").text()).toContain("第 3 / 3 页");
  });

  it("redirects the whole page to the chooser when the workspace is gone", async () => {
    for (const path of [
      "/api/workspaces/:wid/overview/summary",
      "/api/workspaces/:wid/overview/trend",
      "/api/workspaces/:wid/overview/sources",
      "/api/workspaces/:wid/bad-cases",
    ]) {
      server.use(
        http.get(path, () =>
          apiError(404, "WORKSPACE_NOT_FOUND", "workspace is gone"),
        ),
      );
    }
    const { router } = await mountPage();

    await vi.waitFor(() => {
      expect(router.currentRoute.value.path).toBe("/workspaces");
      expect(router.currentRoute.value.query.reason).toBe("forbidden");
    });
  });

  it("shows the real API error code in a block error", async () => {
    mockOverviewApi();
    server.use(
      http.get("/api/workspaces/:wid/overview/summary", () =>
        apiError(422, "OBJECT_FILTER_TOO_LARGE", "too many objects"),
      ),
    );
    const { wrapper } = await mountPage();

    expect(wrapper.text()).toContain("OBJECT_FILTER_TOO_LARGE");
    expect(wrapper.text()).not.toContain("OVERVIEW_SUMMARY_UNAVAILABLE");
    expect(
      wrapper.get("[data-testid='ov-context-quota-used']").text(),
    ).toBe("— / —");
    expect(
      wrapper.get("[data-testid='ov-context-quota-percent']").text(),
    ).toBe("—");
    expect(wrapper.get("[data-testid='ov-context-role']").text()).toBe(
      "全局管理员",
    );
  });


  it("paginates the evolution-target side list five per page", async () => {
    const six = Array.from({ length: 6 }, (_, index) => ({
      ...targetItems[0],
      targetId: `target-page-${index + 1}`,
      objectName: `target-${index + 1}`,
      evolvable: 6 - index,
    }));
    mockOverviewApi({
      targets: { ...targetOverview, items: six, total: six.length },
      targetDetail: {
        ...targetDetail,
        target: {
          ...targetDetail.target,
          targetId: "target-page-1",
          objectName: "target-1",
        },
      },
    });
    const { router, wrapper } = await mountPage(`${ws}/overview?tab=targets`);

    expect(wrapper.findAll("[data-testid^='ov-target-side-item-']")).toHaveLength(5);
    await wrapper.get("[data-testid='ov-target-side-next']").trigger("click");
    await flushPromises();

    expect(router.currentRoute.value.query.tpage).toBe("2");
    expect(wrapper.findAll("[data-testid^='ov-target-side-item-']")).toHaveLength(1);
  });

  it("paginates potential cases eight per page", async () => {
    mockOverviewApi();
    server.use(
      http.get("/api/workspaces/:wid/overview/targets/cases", ({ request }) => {
        requests.targetCases.push(request.url);
        const page = Number(
          new URL(request.url).searchParams.get("page") ?? "1",
        );
        return HttpResponse.json({
          items: page === 2 ? targetCases.items : [],
          total: 9,
          page,
          pageSize: 8,
        });
      }),
    );
    const { router, wrapper } = await mountPage(`${ws}/overview?tab=targets`);

    await wrapper.get("[data-testid='ov-target-case-next']").trigger("click");
    await flushPromises();

    expect(router.currentRoute.value.query.page).toBe("2");
    expect(wrapper.findAll("[data-testid='ov-target-case-row']")).toHaveLength(1);
    const casesUrl = new URL(requests.targetCases.at(-1) as string);
    expect(casesUrl.searchParams.get("page")).toBe("2");
  });

  it("filters the potential list by a clicked target bucket", async () => {
    mockOverviewApi();
    const { router, wrapper } = await mountPage(`${ws}/overview?tab=targets`);

    await wrapper.get("[data-bucket='2026-11-09']").trigger("click");
    await flushPromises();

    expect(router.currentRoute.value.query.cfrom).toBe("2026-11-09");
    expect(router.currentRoute.value.query.cto).toBe("2026-11-15");
    expect(router.currentRoute.value.query.range).toBe("90");
    const casesUrl = new URL(requests.targetCases.at(-1) as string);
    expect(casesUrl.searchParams.get("from")).toBe("2026-11-09");
    expect(casesUrl.searchParams.get("to")).toBe("2026-11-15");
  });

  it("keeps the detail card filter independent from the shared trend", async () => {
    mockOverviewApi({
      targetDetail: {
        ...targetDetail,
        target: {
          ...targetDetail.target,
          targetId: "target-2",
          objectName: "review-agent",
          versions: ["2026.11.2"],
        },
      },
    });
    const { router, wrapper } = await mountPage(`${ws}/overview?tab=targets`);

    await wrapper
      .get("[data-testid='ov-target-detail-version-2026.11.2']")
      .setValue(true);
    await flushPromises();

    expect(router.currentRoute.value.query.dversions).toBe("2026.11.2");
    const detailUrl = new URL(requests.targetDetail.at(-1) as string);
    expect(detailUrl.searchParams.get("versions")).toBe("2026.11.2");
    expect(detailUrl.searchParams.get("versionLimit")).toBe("5");
    const trendUrl = new URL(requests.targetTrend.at(-1) as string);
    expect(trendUrl.searchParams.has("versions")).toBe(false);

    await wrapper.get("[data-testid='ov-target-detail-target']").setValue("target-2");
    await flushPromises();

    expect(router.currentRoute.value.query.dtarget).toBe("target-2");
    expect(router.currentRoute.value.query.dversions).toBeUndefined();
    expect(router.currentRoute.value.query.range).toBe("90");
  });

  it("prefills the custom window from the current range window", async () => {
    mockOverviewApi({
      summary: {
        ...summary,
        window: { from: "2026-11-10", to: "2026-11-16" },
      },
    });
    const { router, wrapper } = await mountPage(`${ws}/overview?range=7`);

    await wrapper.get("[data-testid='ov-range-custom']").trigger("click");
    await flushPromises();

    expect(router.currentRoute.value.query).toEqual({
      tab: "cases",
      range: "custom",
      grain: "day",
      from: "2026-11-10",
      to: "2026-11-16",
    });
  });
});
