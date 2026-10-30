// @vitest-environment jsdom

import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { createPinia, setActivePinia } from "pinia";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import ErrorsPage from "./Index.vue";
import { demoCoreTree } from "../../components/agent-tree/fixtures/demo-nested";
import { createAppRouter } from "../../router";
import { badCaseFixture } from "../../test/badCases";
import { server } from "../../test/server";
import { useAuthStore } from "../../stores/auth";

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

const issueAnalysis = {
  status: "analyzed_issue" as const,
  probeId: "probe-error",
  attributeType: "error" as const,
  displayState: "analyzed_issue_error" as const,
  result: { summary: "The index file was missing." },
};

const nonIssueTitle = "响应可追溯";
const nonIssueReason = "traceable response: 每条结论都能回指到来源。";
const issueTitle = "索引读取失败";
const issueReason =
  "index read failed: 读取检索索引时抛出 ENOENT，该轮结论没有来源。";

const nonIssue = badCaseFixture({
  badCaseId: "case-nonissue",
  title: nonIssueTitle,
  reason: nonIssueReason,
  analysis: {
    status: "analyzed_nonissue",
    probeId: "probe-nonissue",
    attributeType: null,
    displayState: "analyzed_nonissue",
    result: {
      reason: "Every claim has a source.",
      reasoning: ["A source is present.", "No contradiction found."],
    },
  },
});

const issue = badCaseFixture({
  badCaseId: "case-error",
  title: issueTitle,
  reason: issueReason,
  objectType: "agent",
  objectName: "Explore",
  metaData: { file: "src/index.ts", line: 42, error: "ENOENT" },
  analysis: issueAnalysis,
});

const problems = [nonIssue, issue];
const wrappers: VueWrapper[] = [];

function mockApi(items = problems) {
  const tree = { ...demoCoreTree, sessionId: "root-1" };
  server.use(
    http.get("/api/sessions/:id", () =>
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
    http.get("/api/sessions/:id/bad-cases", () =>
      HttpResponse.json({ items }),
    ),
    http.get("/api/sessions/:id/tree", () => HttpResponse.json(tree)),
    http.get("/api/bad-cases/:caseId", ({ params }) => {
      const item = items.find((candidate) => candidate.badCaseId === params.caseId);
      if (!item) {
        return HttpResponse.json(
          { error: { code: "BAD_CASE_NOT_FOUND", message: "missing" } },
          { status: 404 },
        );
      }
      return HttpResponse.json(item);
    }),
    http.get("/api/bad-cases/:caseId/analysis", ({ params }) => {
      const item = items.find((candidate) => candidate.badCaseId === params.caseId);
      if (!item) {
        return HttpResponse.json(
          { error: { code: "BAD_CASE_NOT_FOUND", message: "missing" } },
          { status: 404 },
        );
      }
      return HttpResponse.json(item.analysis);
    }),
    http.get("/api/probes/:probeId", ({ params }) =>
      HttpResponse.json({
        probeId: params.probeId,
        sessionId: "root-1",
        probeType: "agent",
        probeObject: "Explore",
        objectVersion: "v1.0.0",
        attributeType: "error",
        probeDescription: "The index file was not checked.",
        probeAnalysis:
          "1. Locate the read step.\n\n```ts\nconst value = read(id)\n```\n\n[source](https://example.com)",
        createdAt: "2026-10-20T08:46:00+08:00",
        updatedAt: "2026-10-20T08:47:00+08:00",
        fromBadCases: ["case-error"],
        fromBadCasesCount: 1,
      }),
    ),
  );
}

async function mountPage(path = "/sessions/root-1/errors") {
  const pinia = createPinia();
  setActivePinia(pinia);
  useAuthStore().setSession({
    accessToken: "access",
    expiresIn: 1_800,
    user: {
      id: "u-1",
      username: "admin",
      displayName: "管理员",
      role: "admin",
      mustChangePassword: false,
    },
  });
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
  await flushPromises();
  return { router, wrapper };
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount();
  server.resetHandlers();
});
afterAll(() => server.close());

describe("error detail page", () => {
  it("shows the prototype shell and writes case/tab when selecting", async () => {
    mockApi();
    const { router, wrapper } = await mountPage();

    expect(wrapper.get(".error-heading h1").text()).toBe("错误详情");
    expect(wrapper.get(".error-sidebar").text()).toContain("原型错误详情");
    expect(
      wrapper.get("[data-testid='error-root-session-id']").text(),
    ).toBe("根会话 ID · root-1");
    expect(
      wrapper.get("[data-testid='error-meta-root-session-id']").text(),
    ).toContain("根会话 ID · root-1");
    expect(wrapper.get(".error-sidebar").text()).toContain("返回 Session");
    expect(wrapper.find(".problem-list-head").exists()).toBe(false);
    expect(wrapper.get(".all-errors").text()).toContain("全部错误");
    expect(wrapper.get(".all-errors").text()).toContain("2");
    expect(wrapper.findAll("[data-bad-case-id]")).toHaveLength(2);
    expect(wrapper.get(".detail-panel").text()).toContain("问题描述");
    expect(wrapper.get(".detail-panel").text()).toContain("归因分析");
    expect(wrapper.get(".detail-panel").text()).toContain(
      "从左侧选择一个错误，查看问题描述与归因分析。",
    );

    await wrapper.get("[data-bad-case-id='case-error']").trigger("click");
    await flushPromises();

    expect(router.currentRoute.value.fullPath).toBe(
      "/sessions/root-1/errors?case=case-error&tab=desc",
    );
    expect(wrapper.text()).toContain(issueTitle);
    expect(wrapper.get(".description .problem-title").text()).toBe(issueTitle);
    expect(wrapper.get(".description .problem-detail").text()).toBe(
      issueReason,
    );
    expect(
      wrapper.get(".description").text().match(/index read failed/g),
    ).toHaveLength(1);
    expect(wrapper.get(".flow-head span").text()).toBe(
      `仅显示 #2 · ${issueTitle}`,
    );
    const detailId = wrapper.get(".description .problem-id");
    expect(detailId.text()).toBe("case-err");
    expect(detailId.attributes("title")).toBe("case-error");
    expect(detailId.attributes("href")).toBe(
      "/sessions/root-1/errors?case=case-error&tab=desc",
    );
    expect(detailId.attributes("target")).toBe("_blank");
    expect(detailId.attributes("rel")).toBe("noopener noreferrer");
    expect(detailId.attributes("aria-label")).toBe(
      "问题 case-err，在新窗口打开问题描述",
    );
    expect(wrapper.find(".description .field-label").exists()).toBe(false);
    const reportLink = wrapper.get(".description .report-id");
    expect(reportLink.text()).toBe("probe-er");
    expect(reportLink.attributes("title")).toBe("probe-error");
    expect(reportLink.attributes("href")).toBe(
      "/sessions/root-1/errors?case=case-error&tab=attr",
    );
    expect(reportLink.attributes("target")).toBe("_blank");
    expect(reportLink.attributes("rel")).toBe("noopener noreferrer");
    expect(reportLink.attributes("aria-label")).toBe(
      "归因报告 probe-er，在新窗口打开归因分析",
    );
    const firstFact = wrapper.get(".fact-chip");
    expect(firstFact.get(".fact-key").text()).toBe("file");
    expect(firstFact.get(".fact-value").text()).toBe("src/index.ts");
  });

  it("restores case and attribution tab from a refresh URL", async () => {
    mockApi();
    const { wrapper } = await mountPage(
      "/sessions/root-1/errors?case=case-error&tab=attr",
    );

    expect(wrapper.text()).toContain("是问题-错误");
    expect(wrapper.text()).toContain("The index file was not checked.");
    expect(wrapper.get(".conclusion strong").text()).toBe("问题");
    expect(wrapper.get(".conclusion .state-chip").text()).toBe(
      "是问题-错误",
    );
    expect(wrapper.get(".classification").text()).toContain(
      "Explore @ v1.0.0",
    );
    expect(
      wrapper.get(".attribution").text().match(/Explore @ v1\.0\.0/g),
    ).toHaveLength(1);
    const sourceLink = wrapper.get(".source-links a");
    expect(sourceLink.text()).toBe("case-err");
    expect(sourceLink.attributes("title")).toBe("case-error");
    expect(sourceLink.attributes("href")).toBe(
      "/sessions/root-1/errors?case=case-error&tab=desc",
    );
    expect(sourceLink.attributes("target")).toBe("_blank");
    expect(sourceLink.attributes("rel")).toBe("noopener noreferrer");
    expect(sourceLink.attributes("aria-label")).toBe(
      "来源问题 case-err，在新窗口打开问题描述",
    );
    expect(wrapper.find(".markdown pre").exists()).toBe(true);
    expect(wrapper.get(".markdown a").attributes("target")).toBe("_blank");
    expect(wrapper.get(".markdown a").attributes("rel")).toBe(
      "noopener noreferrer",
    );
  });

  it("uses the prototype's exact prompt category and status copy", async () => {
    const promptIssue = badCaseFixture({
      badCaseId: "case-prompt",
      title: "prompt 缺少校验",
      reason: "prompt missed validation: prompt 没有要求校验输出结构。",
      analysis: {
        status: "analyzed_issue",
        probeId: "probe-prompt",
        attributeType: "prompt",
        displayState: "analyzed_issue_prompt",
        result: { summary: "The prompt omitted validation." },
      },
    });
    mockApi([promptIssue]);
    server.use(
      http.get("/api/probes/:probeId", ({ params }) =>
        HttpResponse.json({
          probeId: params.probeId,
          sessionId: "root-1",
          probeType: "agent",
          probeObject: "Explore",
          objectVersion: "v1.0.0",
          attributeType: "prompt",
          probeDescription: "The prompt omitted validation.",
          probeAnalysis: "The prompt did not request validation.",
          createdAt: "2026-10-20T08:46:00+08:00",
          updatedAt: "2026-10-20T08:47:00+08:00",
          fromBadCases: ["case-prompt"],
          fromBadCasesCount: 1,
        }),
      ),
    );
    const { wrapper } = await mountPage(
      "/sessions/root-1/errors?case=case-prompt&tab=attr",
    );

    expect(wrapper.get(".conclusion .state-chip").text()).toBe(
      "是问题-prompt缺失某些提示词",
    );
    expect(wrapper.get(".classification .state-chip").text()).toBe(
      "prompt缺失某些提示词",
    );
    expect(wrapper.get(".description .problem-title").text()).toBe(
      "prompt 缺少校验",
    );
    expect(wrapper.get(".description .problem-detail").text()).toBe(
      "prompt missed validation: prompt 没有要求校验输出结构。",
    );
  });

  it("uses accessible tabs with roving focus and control relationships", async () => {
    mockApi();
    const { router, wrapper } = await mountPage(
      "/sessions/root-1/errors?case=case-error&tab=desc",
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
    await flushPromises();

    expect(router.currentRoute.value.query.tab).toBe("attr");
    expect(wrapper.get("#attr-tab").attributes("tabindex")).toBe("0");
    expect(wrapper.get("#attr-panel").attributes("aria-labelledby")).toBe(
      "attr-tab",
    );
  });

  it("orders non-issue reason before reasoning and keeps tabs URL-driven", async () => {
    mockApi();
    const { router, wrapper } = await mountPage(
      "/sessions/root-1/errors?case=case-nonissue&tab=attr",
    );

    const content = wrapper.get(".attribution").text();
    expect(wrapper.get(".conclusion strong").text()).toBe("非问题");
    expect(wrapper.get(".conclusion .state-chip").text()).toBe("非问题");
    expect(wrapper.get(".description .problem-title").text()).toBe(
      nonIssueTitle,
    );
    expect(wrapper.get(".description .problem-detail").text()).toBe(
      nonIssueReason,
    );
    expect(wrapper.get(".conclusion").text()).not.toContain(
      "Every claim has a source.",
    );
    expect(
      content.match(/Every claim has a source\./g),
    ).toHaveLength(1);
    expect(content.indexOf("非问题的分析原因")).toBeLessThan(
      content.indexOf("分析推导过程"),
    );
    expect(content).toContain("A source is present.");

    await wrapper.get("#desc-tab").trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query).toEqual({
      case: "case-nonissue",
      tab: "desc",
    });
  });

  it("renders a page-level mismatch for a cross-session problem", async () => {
    mockApi();
    server.use(
      http.get("/api/bad-cases/:caseId", () =>
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
      "/sessions/root-1/errors?case=case-error&tab=desc",
    );

    expect(wrapper.text()).toContain("问题不属于当前 Session");
    expect(wrapper.find(".page-error button").exists()).toBe(false);
    expect(wrapper.find("[data-testid='errors-agent-tree']").exists()).toBe(false);
  });

  it("renders a non-retryable page state when the problem no longer exists", async () => {
    mockApi();
    server.use(
      http.get("/api/bad-cases/:caseId", () =>
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
      "/sessions/root-1/errors?case=case-error&tab=desc",
    );

    expect(wrapper.text()).toContain("问题不存在或已删除");
    expect(wrapper.find(".page-error button").exists()).toBe(false);
  });

  it("retries a transient detail failure and restores the workspace", async () => {
    mockApi();
    let detailAttempts = 0;
    let analysisAttempts = 0;
    server.use(
      http.get("/api/bad-cases/:caseId", () => {
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
      http.get("/api/bad-cases/:caseId/analysis", () => {
        analysisAttempts += 1;
        return analysisAttempts === 1
          ? HttpResponse.json(
              {
                error: {
                  code: "BAD_CASE_ANALYSIS_UNAVAILABLE",
                  message: "temporarily unavailable",
                },
              },
              { status: 503 },
            )
          : HttpResponse.json(issue.analysis);
      }),
    );
    const { wrapper } = await mountPage(
      "/sessions/root-1/errors?case=case-error&tab=desc",
    );

    expect(wrapper.text()).toContain("问题详情读取失败，请重试");
    await wrapper.get(".page-error button").trigger("click");
    await flushPromises();

    expect(wrapper.find(".page-error").exists()).toBe(false);
    expect(wrapper.get(".description .problem-title").text()).toBe(issueTitle);
    expect(wrapper.get(".description .problem-detail").text()).toBe(
      issueReason,
    );
    expect(detailAttempts).toBe(2);
    expect(analysisAttempts).toBe(2);
  });

  it("keeps machine diagnostic codes out of degraded problem details", async () => {
    const degraded = badCaseFixture({
      badCaseId: "case-degraded",
      degraded: true,
      diagnosticCode: "BAD_CASE_DISPLAY_STATE_UNKNOWN",
    });
    mockApi([degraded]);
    const { wrapper } = await mountPage(
      "/sessions/root-1/errors?case=case-degraded&tab=desc",
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

  it("shows the unanalyzed placeholder without requesting a probe", async () => {
    const unanalyzed = badCaseFixture({
      badCaseId: "case-unanalyzed",
      title: "尚未归因",
      reason:
        "这一条问题还没有完成归因分析，描述正文仍然完整保留。",
    });
    mockApi([unanalyzed]);
    const { wrapper } = await mountPage(
      "/sessions/root-1/errors?case=case-unanalyzed&tab=attr",
    );

    expect(wrapper.get(".description .problem-title").text()).toBe(
      "尚未归因",
    );
    expect(wrapper.get(".description .problem-detail").text()).toBe(
      "这一条问题还没有完成归因分析，描述正文仍然完整保留。",
    );
    expect(wrapper.text()).toContain("尚未分析");
    expect(wrapper.get(".conclusion").text()).toBe("结论尚未分析未分析");
    expect(wrapper.get(".unanalyzed-note").text()).toBe(
      "该错误还没有归因分析，尚不能判断是否为问题。",
    );
    expect(wrapper.get(".conclusion").text()).not.toContain(
      "该错误还没有归因分析",
    );
  });

  it("does not request a probe until the attribution tab is active", async () => {
    mockApi();
    const probeRequests: string[] = [];
    server.use(
      http.get("/api/probes/:probeId", ({ params }) => {
        probeRequests.push(String(params.probeId));
        return HttpResponse.json({
          probeId: params.probeId,
          sessionId: "root-1",
          probeType: "agent",
          probeObject: "Explore",
          objectVersion: "v1.0.0",
          attributeType: "error",
          probeDescription: "The index file was not checked.",
          probeAnalysis: "Checked the index.",
          createdAt: "2026-10-20T08:46:00+08:00",
          updatedAt: "2026-10-20T08:47:00+08:00",
          fromBadCases: ["case-error"],
          fromBadCasesCount: 1,
        });
      }),
    );
    const { router } = await mountPage(
      "/sessions/root-1/errors?case=case-error&tab=desc",
    );

    expect(probeRequests).toEqual([]);
    await router.push(
      "/sessions/root-1/errors?case=case-error&tab=attr",
    );
    await flushPromises();

    expect(probeRequests).toEqual(["probe-error"]);
  });

  it("clears the case and restores the complete graph via all errors", async () => {
    mockApi();
    const { router, wrapper } = await mountPage(
      "/sessions/root-1/errors?case=case-error&tab=attr",
    );

    await wrapper.get(".all-errors").trigger("click");
    await flushPromises();

    expect(router.currentRoute.value.fullPath).toBe("/sessions/root-1/errors");
    expect(
      wrapper.get("[data-testid='errors-agent-tree']").text(),
    ).toContain("badcases:2");
  });
});
