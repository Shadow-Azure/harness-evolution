// @vitest-environment jsdom

/* eslint-disable vue/one-component-per-file -- Mocks are declared inline for this page. */

import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { createPinia, setActivePinia } from "pinia";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import type {
  AttributionDetail,
  BadCase,
  WorkspaceRole,
} from "@harness/contracts";

import ErrorsPage from "./Index.vue";
import { demoCoreTree } from "../../components/agent-tree/fixtures/demo-nested";
import { createAppRouter } from "../../router";
import { badCaseFixture } from "../../test/badCases";
import { server } from "../../test/server";
import { signInWithWorkspace, testWorkspace } from "../../test/auth";

const workspaceId = "ws-test";
const ws = `/workspaces/${workspaceId}`;
const sessionsBase = `/api/workspaces/${workspaceId}/sessions`;
const badCasesBase = `/api/workspaces/${workspaceId}/bad-cases`;

vi.mock("../../components/agent-tree/AgentTree.vue", async () => {
  const { defineComponent, h } = await import("vue");
  const AgentTree = defineComponent({
    name: "AgentTree",
    props: {
      tree: { type: Object, required: true },
      expanded: { type: Array, default: () => [] },
      activeBadCaseId: { type: String, default: null },
      problems: { type: Array, default: () => [] },
    },
    emits: ["badcase-select", "toggle-expanded"],
    setup(props, { emit }) {
      return () => h("div", { "data-testid": "errors-agent-tree" }, [
        h("span", `badcases:${props.problems.length}`),
        h("span", `active:${props.activeBadCaseId ?? "none"}`),
        h(
          "button",
          {
            type: "button",
            onClick: () => {
              const first = props.problems[0] as { badCaseId: string } | undefined;
              if (first) emit("badcase-select", first.badCaseId);
            },
          },
          "select graph problem",
        ),
      ]);
    },
  });
  return {
    __esModule: true,
    __isKeepAlive: false,
    __isTeleport: false,
    default: AgentTree,
  };
});

vi.mock("../evolution/components/LaunchWizard.vue", async () => {
  const { defineComponent, h } = await import("vue");
  const LaunchWizard = defineComponent({
    name: "LaunchWizard",
    props: {
      wid: { type: String, required: true },
      focusCaseId: { type: String, default: null },
    },
    emits: ["close", "launched"],
    setup(props, { emit }) {
      return () =>
        h(
          "div",
          {
            "data-testid": "launch-wizard-stub",
            "data-focus-case-id": props.focusCaseId ?? "",
          },
          [
            h(
              "button",
              { type: "button", onClick: () => emit("close") },
              "close wizard",
            ),
          ],
        );
    },
  });
  return {
    __esModule: true,
    __isKeepAlive: false,
    __isTeleport: false,
    default: LaunchWizard,
  };
});

const issue = badCaseFixture({
  badCaseId: "case-error",
  title: "索引读取失败",
  reason:
    "index read failed: 读取检索索引时抛出 ENOENT，该轮结论没有来源。",
  objectType: "agent",
  objectName: "Explore",
  attributionCount: 4,
  hasAttribution: true,
  metaData: { file: "src/index.ts", line: 42, error: "ENOENT" },
});

const noAttribution = badCaseFixture({
  badCaseId: "case-unanalyzed",
  title: "尚未归因",
  reason: "这一条问题还没有完成归因分析，描述正文仍然完整保留。",
  attributionCount: 0,
  hasAttribution: false,
});
const problems = [noAttribution, issue];

function attribution(
  overrides: Partial<AttributionDetail> = {},
): AttributionDetail {
  const base: AttributionDetail = {
    attributionId: "AT-0001",
    badCaseId: "case-error",
    objectType: "skill",
    objectName: "checklist-skill",
    objectVersion: "2026.11.1",
    conclusion: "attributed",
    category: "error",
    confidence: 0.86,
    runId: null,
    isCached: false,
    reusedCount: 0,
    createdAt: "2026-10-20T09:05:00+08:00",
    updatedAt: "2026-10-20T09:05:00+08:00",
    reason: "检查清单技能把未完成项误判为通过。",
    reasoning:
      "1. 定位 checklist-skill。\n\n```ts\nconst done = true\n```\n\n[证据](https://example.com)",
    policyVersion: "v2",
    attributionEngine: "m11-02-smoke",
    triggerCompare: {
      objectTriggerAt: "2026-10-20T09:02:00+08:00",
      caseTriggerAt: "2026-10-20T09:03:00+08:00",
      order: "after",
      versionState: "exact",
    },
    warnings: [],
  };
  return { ...base, ...overrides };
}

const attributions: AttributionDetail[] = [
  attribution({
    attributionId: "AT-0001",
    objectName: "project-knowledge",
    objectType: "knowledge",
    objectVersion: null,
    category: "prompt",
    createdAt: "2026-10-20T09:07:00+08:00",
    triggerCompare: {
      objectTriggerAt: null,
      caseTriggerAt: null,
      order: "unknown",
      versionState: "unknown",
    },
    warnings: [
      {
        code: "ATTRIBUTION_VERSION_UNKNOWN",
        message: "The attribution has no pinned object version.",
      },
    ],
  }),
  attribution({
    attributionId: "AT-0002",
    objectName: "review-agent",
    objectType: "agent",
    conclusion: "non_target",
    category: null,
    confidence: 0.74,
    createdAt: "2026-10-20T09:06:00+08:00",
    reason: "review-agent 的触发点在 bad case 之后。",
    triggerCompare: {
      objectTriggerAt: null,
      caseTriggerAt: null,
      order: "unknown",
      versionState: "exact",
    },
  }),
  attribution({
    attributionId: "AT-0003",
    objectName: "checklist-skill",
    createdAt: "2026-10-20T09:05:00+08:00",
  }),
  attribution({
    attributionId: "AT-0004",
    objectName: "legacy-probe",
    objectVersion: "synthetic-1",
    createdAt: "2026-10-20T09:03:30+08:00",
    isCached: true,
    reusedCount: 2,
    runId: "run-1",
    triggerCompare: {
      objectTriggerAt: "2026-10-20T09:04:00+08:00",
      caseTriggerAt: "2026-10-20T09:03:00+08:00",
      order: "before",
      versionState: "exact",
    },
  }),
];

const wrappers: VueWrapper[] = [];

function mockApi(items: BadCase[] = problems) {
  const tree = { ...demoCoreTree, sessionId: "root-1" };
  server.use(
    http.get(`${sessionsBase}/:id`, () =>
      HttpResponse.json({
        id: "root-1",
        title: "原型错误详情",
        short: "原型错误详情",
        repo: "harness-evolution",
        startedAt: "2026-10-20T08:46:00+08:00",
        durationSeconds: 540,
        model: "claude-sonnet-4.5",
        status: "partial",
        skills: [],
        stats: {
          agents: 1,
          badCases: items.length,
          badCasesPer100Messages: 1,
          errors: 1,
          failPer100Messages: 1,
          messages: 10,
          tokens: 1_000,
          tools: 1,
          userTurns: 1,
        },
      }),
    ),
    http.get(`${sessionsBase}/:id/bad-cases`, () =>
      HttpResponse.json({ items }),
    ),
    http.get(`${sessionsBase}/:id/tree`, () => HttpResponse.json(tree)),
    http.get(`${badCasesBase}/:caseId`, ({ params }) => {
      const item = items.find((candidate) => candidate.badCaseId === params.caseId);
      if (!item) {
        return HttpResponse.json(
          { error: { code: "BAD_CASE_NOT_FOUND", message: "missing" } },
          { status: 404 },
        );
      }
      return HttpResponse.json(item);
    }),
    http.get(`${badCasesBase}/:caseId/attributions`, ({ params, request }) => {
      const url = new URL(request.url);
      const page = Number(url.searchParams.get("page") ?? 1);
      const pageSize = Number(url.searchParams.get("pageSize") ?? 2);
      const rows =
        params.caseId === "case-error" ? attributions : [];
      const start = (page - 1) * pageSize;
      return HttpResponse.json({
        items: rows.slice(start, start + pageSize),
        total: rows.length,
        page,
        pageSize,
      });
    }),
    http.get(
      `${badCasesBase}/:caseId/attributions/:attributionId`,
      ({ params }) => {
        const item = attributions.find(
          (candidate) =>
            candidate.attributionId === params.attributionId &&
            candidate.badCaseId === params.caseId,
        );
        if (!item) {
          return HttpResponse.json(
            {
              error: {
                code: "ATTRIBUTION_NOT_FOUND",
                message: "not found",
              },
            },
            { status: 404 },
          );
        }
        return HttpResponse.json(item);
      },
    ),
  );
}

async function settle(): Promise<void> {
  for (let index = 0; index < 6; index += 1) {
    await flushPromises();
  }
}

async function mountPage(
  path = `${ws}/sessions/root-1/errors`,
  role: WorkspaceRole = "global_admin",
) {
  const pinia = createPinia();
  setActivePinia(pinia);
  signInWithWorkspace(undefined, [testWorkspace({ role })]);
  const router = createAppRouter();
  await router.push(path);
  await router.isReady();
  const wrapper = mount(ErrorsPage, {
    global: {
      plugins: [
        [VueQueryPlugin, {
          queryClient: new QueryClient({
            defaultOptions: { queries: { gcTime: 0, retry: false } },
          }),
        }],
        pinia,
        router,
      ],
    },
  });
  wrappers.push(wrapper);
  await settle();
  return { router, wrapper };
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount();
  server.resetHandlers();
});
afterAll(() => server.close());

describe("error detail page", () => {
  it("renders folded bad-case groups, filters and explicit deep links", async () => {
    mockApi();
    const { router, wrapper } = await mountPage();

    expect(wrapper.get(".error-heading h1").text()).toBe("错误详情");
    expect(wrapper.get(".error-sidebar").text()).toContain("原型错误详情");
    expect(wrapper.get(".error-sidebar").text()).toContain("bad case");
    expect(
      wrapper.get("[data-testid='error-root-session-id']").text(),
    ).toBe("根会话 ID · root-1");
    expect(
      wrapper.get("[data-testid='error-meta-root-session-id']").text(),
    ).toContain("根会话 ID · root-1");
    expect(wrapper.get(".error-meta").text()).toContain("2 个 bad case");
    expect(wrapper.get(".error-meta").text()).toContain("1 个已归因");
    expect(wrapper.findAll("[data-testid='case-group']")).toHaveLength(2);
    expect(wrapper.get(".sidebar-filter").text()).toContain("有归因 1");
    expect(wrapper.get(".sidebar-filter").text()).toContain("待归因 1");
    expect(wrapper.get("[data-testid='all-bad-cases']").text()).toContain(
      "全部 bad case",
    );
    expect(wrapper.get(".detail-panel").text()).toContain(
      "从左侧选择一个 bad case，查看问题描述与归因分析。",
    );

    const titleLink = wrapper.get(
      "[data-bad-case-id='case-error'] [data-testid='case-title-link']",
    );
    expect(titleLink.attributes("href")).toBe(
      `${ws}/sessions/root-1/errors?case=case-error&tab=desc`,
    );
    const idLink = wrapper.get(
      "[data-bad-case-id='case-error'] [data-testid='case-id']",
    );
    expect(idLink.text()).toBe("case-err");
    expect(idLink.attributes("title")).toBe("case-error");
    expect(idLink.attributes("target")).toBe("_blank");
    expect(idLink.attributes("rel")).toBe("noopener noreferrer");

    await titleLink.trigger("click");
    await settle();

    expect(router.currentRoute.value.fullPath).toBe(
      `${ws}/sessions/root-1/errors?case=case-error&tab=desc`,
    );
    const group = wrapper.get("[data-bad-case-id='case-error']");
    expect(group.text()).toContain("归因分析 · 按进化对象");
    expect(
      group.findAll("[data-testid='attribution-item']"),
    ).toHaveLength(2);
    expect(group.get("[data-testid='attribution-item']").text()).toContain(
      "project-knowledge",
    );
    expect(group.get("[data-testid='attribution-item']").text()).toContain(
      "可归因",
    );
    expect(group.text()).toContain("1 / 2");
    expect(wrapper.get("#attr-tab").text()).toBe("归因分析 (4)");
    expect(wrapper.get(".flow-head span").text()).toBe(
      "仅显示 #2 · 索引读取失败",
    );
  });

  it("restores case, tab and at from a refresh URL and navigates between attributions", async () => {
    mockApi();
    const { router, wrapper } = await mountPage(
      `${ws}/sessions/root-1/errors?case=case-error&tab=attr&at=AT-0002`,
    );

    expect(wrapper.get("[data-testid='attribution-position']").text()).toBe(
      "2 / 4",
    );
    const report = wrapper.get("[data-testid='attribution-report']");
    expect(report.get(".conclusion strong").text()).toBe("非该对象问题");
    expect(report.get(".conclusion").text()).not.toContain("未分类");
    expect(report.text()).toContain("review-agent");
    expect(report.text()).toContain("触发点无法比较");
    expect(report.text()).toContain("74%");
    expect(report.text()).toContain("v2 · m11-02-smoke");
    expect(report.text()).toContain("结论边界");
    expect(wrapper.get("[data-bad-case-id='case-error'] .attr-item.active").text())
      .toContain("review-agent");

    await wrapper.get("[data-testid='attribution-next']").trigger("click");
    await settle();

    expect(router.currentRoute.value.query.at).toBe("AT-0003");
    expect(wrapper.get("[data-testid='attribution-position']").text()).toBe(
      "3 / 4",
    );
    expect(
      wrapper.get("[data-testid='attribution-report']").text(),
    ).toContain("可归因到本对象");

    await wrapper.get("[data-testid='attribution-prev']").trigger("click");
    await settle();
    expect(router.currentRoute.value.query.at).toBe("AT-0002");
  });

  it("keeps the unknown-version evidence gap visible", async () => {
    mockApi();
    const { wrapper } = await mountPage(
      `${ws}/sessions/root-1/errors?case=case-error&tab=attr&at=AT-0001`,
    );

    const report = wrapper.get("[data-testid='attribution-report']");
    expect(report.text()).toContain("project-knowledge");
    expect(report.text()).toContain("版本未固定");
    expect(report.text()).toContain(
      "该归因没有固定的对象版本，不能视为精确版本命中；轨迹时间戳待重放。",
    );
    expect(report.text()).toContain("ATTRIBUTION_VERSION_UNKNOWN");
  });

  it("paginates each expanded group by two attributions", async () => {
    mockApi();
    const { wrapper } = await mountPage(
      `${ws}/sessions/root-1/errors?case=case-error&tab=desc`,
    );

    const group = wrapper.get("[data-bad-case-id='case-error']");
    expect(group.findAll("[data-testid='attribution-item']")).toHaveLength(2);
    await group.get("[data-testid='attribution-page-next']").trigger("click");
    await settle();

    const next = wrapper.get("[data-bad-case-id='case-error']");
    expect(
      next.findAll("[data-testid='attribution-item']"),
    ).toHaveLength(2);
    expect(next.text()).toContain("checklist-skill");
    expect(next.text()).toContain("legacy-probe");
    expect(next.text()).toContain("缓存");
    expect(next.text()).toContain("2 / 2");
  });

  it("filters the left list without changing the selected detail", async () => {
    mockApi();
    const { wrapper } = await mountPage(
      `${ws}/sessions/root-1/errors?case=case-error&tab=desc`,
    );

    const chips = wrapper.findAll(".sidebar-filter .chip");
    await chips[2]!.trigger("click");
    await settle();
    expect(wrapper.findAll("[data-testid='case-group']")).toHaveLength(1);
    expect(wrapper.get("[data-bad-case-id='case-unanalyzed']")).toBeTruthy();
    expect(wrapper.text()).toContain("索引读取失败");

    await chips[1]!.trigger("click");
    await settle();
    expect(wrapper.findAll("[data-testid='case-group']")).toHaveLength(1);
    expect(wrapper.get("[data-bad-case-id='case-error']")).toBeTruthy();
  });

  it("shows the unanalyzed empty state and opens the wizard for an admin", async () => {
    mockApi();
    const { wrapper } = await mountPage(
      `${ws}/sessions/root-1/errors?case=case-unanalyzed&tab=attr`,
    );

    expect(wrapper.get("[data-testid='attribution-empty']").text()).toContain(
      "尚未归因",
    );
    expect(wrapper.text()).toContain(
      "该 bad case 还没有被任何自进化运行归因",
    );
    expect(wrapper.text()).not.toContain("非该对象问题");
    expect(
      wrapper.find("[data-testid='launch-wizard-stub']").exists(),
    ).toBe(false);

    await wrapper.get("[data-testid='start-evolution-from-case']").trigger(
      "click",
    );
    await settle();
    expect(
      wrapper.get("[data-testid='launch-wizard-stub']").attributes(
        "data-focus-case-id",
      ),
    ).toBe("case-unanalyzed");
  });

  it("hides the start entries from ordinary members", async () => {
    mockApi();
    const { wrapper } = await mountPage(
      `${ws}/sessions/root-1/errors?case=case-unanalyzed&tab=attr`,
      "member",
    );

    expect(wrapper.get("[data-testid='attribution-empty']").text()).toContain(
      "尚未归因",
    );
    expect(
      wrapper.find("[data-testid='start-evolution-from-case']").exists(),
    ).toBe(false);
    expect(
      wrapper.find("[data-testid='case-start-evolution']").exists(),
    ).toBe(false);
  });

  it("opens the attribution tab from the problem description summary", async () => {
    mockApi();
    const { router, wrapper } = await mountPage(
      `${ws}/sessions/root-1/errors?case=case-error&tab=desc`,
    );

    await wrapper.get("[data-testid='problem-attribution-summary']").trigger(
      "click",
    );
    await settle();

    expect(router.currentRoute.value.query.tab).toBe("attr");
    expect(router.currentRoute.value.query.at).toBe("AT-0001");
    expect(
      wrapper.get("[data-testid='attribution-report']").text(),
    ).toContain("project-knowledge");
  });

  it("clears the case and restores the complete graph via all bad cases", async () => {
    mockApi();
    const { router, wrapper } = await mountPage(
      `${ws}/sessions/root-1/errors?case=case-error&tab=attr`,
    );

    await wrapper.get("[data-testid='all-bad-cases']").trigger("click");
    await settle();

    expect(router.currentRoute.value.fullPath).toBe(
      `${ws}/sessions/root-1/errors`,
    );
    expect(wrapper.get(".detail-panel").text()).toContain(
      "从左侧选择一个 bad case，查看问题描述与归因分析。",
    );
    expect(
      wrapper.get("[data-testid='errors-agent-tree']").text(),
    ).toContain("badcases:2");
  });

  it("uses accessible tabs with roving focus and control relationships", async () => {
    mockApi();
    const { router, wrapper } = await mountPage(
      `${ws}/sessions/root-1/errors?case=case-error&tab=desc`,
    );

    const desc = wrapper.get("#desc-tab");
    const attr = wrapper.get("#attr-tab");
    expect(desc.attributes("aria-controls")).toBe("desc-panel");
    expect(desc.attributes("tabindex")).toBe("0");
    expect(attr.attributes("aria-controls")).toBe("attr-panel");
    expect(attr.attributes("tabindex")).toBe("-1");
    expect(wrapper.get("#desc-panel").attributes("role")).toBe("tabpanel");
    expect(wrapper.get("#desc-panel").attributes("aria-labelledby")).toBe(
      "desc-tab",
    );

    await desc.trigger("keydown", { key: "ArrowRight" });
    await settle();

    expect(router.currentRoute.value.query.tab).toBe("attr");
    expect(wrapper.get("#attr-tab").attributes("tabindex")).toBe("0");
    expect(wrapper.get("#attr-panel").attributes("aria-labelledby")).toBe(
      "attr-tab",
    );
  });

  it("renders a page-level mismatch for a cross-session problem", async () => {
    mockApi();
    server.use(
      http.get(`${badCasesBase}/:caseId`, () =>
        HttpResponse.json(
          {
            error: {
              code: "BAD_CASE_SESSION_MISMATCH",
              message: "wrong session",
            },
          },
          { status: 409 },
        ),
      ),
    );
    const { wrapper } = await mountPage(
      `${ws}/sessions/root-1/errors?case=case-error&tab=desc`,
    );

    expect(wrapper.text()).toContain("问题不属于当前 Session");
    expect(wrapper.find(".page-error button").exists()).toBe(false);
    expect(wrapper.find("[data-testid='errors-agent-tree']").exists()).toBe(false);
  });

  it("renders a non-retryable page state when the problem no longer exists", async () => {
    mockApi();
    server.use(
      http.get(`${badCasesBase}/:caseId`, () =>
        HttpResponse.json(
          {
            error: {
              code: "BAD_CASE_NOT_FOUND",
              message: "missing",
            },
          },
          { status: 404 },
        ),
      ),
    );
    const { wrapper } = await mountPage(
      `${ws}/sessions/root-1/errors?case=case-error&tab=desc`,
    );

    expect(wrapper.text()).toContain("问题不存在或已删除");
    expect(wrapper.find(".page-error button").exists()).toBe(false);
  });

  it("retries a transient detail failure and restores the workspace", async () => {
    mockApi();
    let detailAttempts = 0;
    server.use(
      http.get(`${badCasesBase}/:caseId`, () => {
        detailAttempts += 1;
        return detailAttempts === 1
          ? HttpResponse.json(
              {
                error: {
                  code: "BAD_CASE_UNAVAILABLE",
                  message: "temporarily unavailable",
                },
              },
              { status: 503 },
            )
          : HttpResponse.json(issue);
      }),
    );
    const { wrapper } = await mountPage(
      `${ws}/sessions/root-1/errors?case=case-error&tab=desc`,
    );

    expect(wrapper.text()).toContain("问题详情读取失败，请重试");
    await wrapper.get(".page-error button").trigger("click");
    await settle();

    expect(wrapper.find(".page-error").exists()).toBe(false);
    expect(wrapper.get(".description .problem-title").text()).toBe(
      issue.title,
    );
    expect(wrapper.get(".description .problem-detail").text()).toBe(
      issue.reason,
    );
    expect(detailAttempts).toBe(2);
  });

  it("keeps machine diagnostic codes out of degraded problem details", async () => {
    const degraded = badCaseFixture({
      badCaseId: "case-degraded",
      degraded: true,
      diagnosticCode: "BAD_CASE_DISPLAY_STATE_UNKNOWN",
      attributionCount: 0,
      hasAttribution: false,
    });
    mockApi([degraded]);
    const { wrapper } = await mountPage(
      `${ws}/sessions/root-1/errors?case=case-degraded&tab=desc`,
    );

    const description = wrapper.get(".description").text();
    expect(description).toContain("外部字段存在漂移，当前以安全占位展示。");
    expect(description).not.toContain("BAD_CASE_DISPLAY_STATE_UNKNOWN");
    expect(wrapper.get(".description .problem-title").text()).toBe(
      degraded.title,
    );
    expect(wrapper.get(".description .problem-detail").text()).toBe(
      degraded.reason,
    );
    expect(wrapper.get(".description .degraded-chip").text()).toBe("数据降级");
  });

  it("keeps the non-target conclusion text apart from the unanalyzed placeholder", async () => {
    mockApi();
    const { wrapper } = await mountPage(
      `${ws}/sessions/root-1/errors?case=case-error&tab=attr&at=AT-0002`,
    );

    const report = wrapper.get("[data-testid='attribution-report']");
    expect(report.text()).toContain("非该对象问题");
    expect(report.text()).not.toContain("尚未归因");
    expect(report.text()).not.toContain("非问题");
  });
});
