// @vitest-environment jsdom

import type {
  AttributionPreviewResult,
  PotentialPreviewResult,
  SessionPreviewResult,
} from "@harness/contracts";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { http, HttpResponse } from "msw";
import { createPinia, setActivePinia } from "pinia";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";

import { server } from "../../../test/server";
import LaunchWizard from "./LaunchWizard.vue";

const workspaceId = "ws-test";
const ws = `/workspaces/${workspaceId}`;
const apiBase = `/api/workspaces/${workspaceId}/evolution`;
const catalogsBase = `/api/workspaces/${workspaceId}/catalogs`;

const wrappers: VueWrapper[] = [];

const resolvedRevision =
  "digest:9080a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789ab";

const sessionPreview: SessionPreviewResult = {
  summary: {
    reported: 6,
    associated: 2,
    skipped: 3,
    versionUnresolved: 1,
    pending: 0,
  },
  items: [
    {
      sessionId: "session-0001",
      short: "研究 session",
      title: "研究 session",
      objectTriggerAt: "2026-10-20T09:00:00+08:00",
      badCaseCount: 2,
    },
    {
      sessionId: "session-0002",
      short: "评审 session",
      title: "评审 session",
      objectTriggerAt: "2026-10-21T10:00:00+08:00",
      badCaseCount: 1,
    },
  ],
  total: 2,
  page: 1,
  pageSize: 4,
  targetRevision: resolvedRevision,
};

const potentialPreview: PotentialPreviewResult = {
  summary: {
    badCases: 5,
    potential: 2,
    byReason: {
      selfReport: 1, customSource: 0,
      afterObject: 1,
      both: 0,
      orderUnknown: 1,
      policyExcluded: 3,
    },
  },
  items: [
    {
      badCaseId: "case-0001",
      objectName: "deep-research",
      badCaseType: "self",
      triggerAt: "2026-10-20T09:02:00+08:00",
      sessionId: "session-0001",
      hitReason: "self_report",
      orderState: "comparable",
      anchorSource: "event",
    },
    {
      badCaseId: "case-0002",
      objectName: "deep-research",
      badCaseType: "discovery",
      triggerAt: "2026-10-21T10:02:00+08:00",
      sessionId: "session-0002",
      hitReason: "after_object",
      orderState: "unknown",
      anchorSource: "post_process",
    },
  ],
  total: 2,
  page: 1,
  pageSize: 5,
  targetRevision: resolvedRevision,
};

const attributionPreview: AttributionPreviewResult = {
  usesBoundSkill: true,
  canRecompute: true,
  summary: { potential: 2, reused: 1, fresh: 0, missing: 1, bySkill: {"attribute-badcases": 1}, nonTargetKnown: 0 },
  targetRevision: resolvedRevision,
};

const contentTimeoutError = {
  error: {
    code: "TARGET_CONTENT_UNRESOLVED",
    message: "target content could not be resolved to a body hash",
    details: {
      targetType: "skill",
      reason: "content_timeout",
    },
  },
};

const targetCatalog = {
  skill: [
    {
      id: "tgt-1",
      name: "deep-research",
      repoUrl: "https://git.example.com/skills.git",
      subDir: "skills/deep-research",
      defaultRef: "v2.0.0",
      versions: ["v2.0.0", "v1.9.0"],
    },
  ],
  agent: [
    {
      id: "tgt-2",
      name: "Explore",
      repoUrl: "https://git.example.com/agents.git",
      subDir: "agents/explore",
      defaultRef: "v1.0.0",
      versions: ["v1.0.0"],
    },
  ],
};

const focusBadCase = {
  badCaseId: "case-focus",
  badCaseType: "self",
  sessionId: "session-0001",
  sessionTitle: "研究 session",
  objectName: "deep-research",
  objectType: "skill",
  objectVersion: "v1.9.0",
  title: "焦点问题",
  reason: "焦点问题描述",
  anchor: { agentId: "agent-1", eventIndex: 0, kind: "event" },
  badCaseAgent: { agentId: "agent-1", sessionId: "session-0001" },
  analysis: { status: "unanalyzed" },
  degraded: false,
  diagnosticCode: null,
  metaData: null,
};

type HandlerOptions = {
  sessions?: () => Response | Promise<Response>;
  potential?: () => Response | Promise<Response>;
  attribution?: () => Response | Promise<Response>;
  full?: () => Response | Promise<Response>;
  cluster?: () => Response | Promise<Response>;
  catalog?: unknown;
  catalogError?: boolean;
};

function useHandlers(options: HandlerOptions = {}): void {
  server.use(
    http.get(`${catalogsBase}/targets`, () =>
      options.catalogError
        ? HttpResponse.json(
            { error: { code: "INTERNAL", message: "catalog unavailable" } },
            { status: 500 },
          )
        : HttpResponse.json(options.catalog ?? targetCatalog),
    ),
    http.get(`/api${ws}/attribution-skill-packages`, () =>
      HttpResponse.json({ items: [{ id: "default-attribute-badcases", skillName: "attribute-badcases" }] }),
    ),
    http.get(`${apiBase}/targets/tgt-1/versions`, () =>
      HttpResponse.json({
        versions: ["v2.0.0", "v1.9.0"],
        defaultRef: "v2.0.0",
      }),
    ),
    http.get(`${apiBase}/targets/tgt-1/attribution-skill`, () =>
      HttpResponse.json({
        id: "revision-platform-1",
        skillId: "skill-platform",
        workspaceId: null,
        skillKey: "platform-default",
        displayName: "平台默认归因",
        description: "固定规则归因",
        builtIn: true,
        enabled: true,
        revision: 1,
        content: { engine: "rule-v1" },
        contentHash: "a".repeat(64),
        executorType: "builtin_rule",
        outputSchemaVersion: "probe-report/v2",
        status: "published",
        source: "platform",
      }),
    ),
    http.get(`/api${ws}/bad-cases/case-focus`, () =>
      HttpResponse.json(focusBadCase),
    ),
    http.post(`${apiBase}/preview/sessions`, () =>
      options.sessions
        ? options.sessions()
        : HttpResponse.json(sessionPreview),
    ),
    http.post(`${apiBase}/preview/potential`, () =>
      options.potential
        ? options.potential()
        : HttpResponse.json(potentialPreview),
    ),
    http.post(`${apiBase}/preview/attribution`, () =>
      options.attribution
        ? options.attribution()
        : HttpResponse.json(attributionPreview),
    ),
    http.post(`${apiBase}/runs`, () =>
      options.full
        ? options.full()
        : HttpResponse.json(
            { runId: "run-full", jobId: "job-full", status: "preparing" },
            { status: 202 },
          ),
    ),
    http.post(`${apiBase}/cluster-previews`, () =>
      options.cluster
        ? options.cluster()
        : HttpResponse.json(
            {
              runId: "run-cluster",
              jobId: "job-cluster",
              status: "preparing",
            },
            { status: 202 },
          ),
    ),
  );
}

async function mountWizard(focusCaseId?: string) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/:pathMatch(.*)*", component: { template: "<div />" } }],
  });
  await router.push("/");
  await router.isReady();
  const wrapper = mount(LaunchWizard, {
    props: focusCaseId ? { wid: workspaceId, focusCaseId } : { wid: workspaceId },
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
  wrappers.push(wrapper);
  await flushPromises();
  return { wrapper, router };
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount();
  server.resetHandlers();
});
afterAll(() => server.close());

async function fillStep1(wrapper: VueWrapper): Promise<void> {
  await wrapper.get("[data-testid='wizard-target']").setValue("tgt-1");
  await wrapper.get("[data-testid='wizard-version']").setValue("v2.0.0");
  await wrapper.get("[data-testid='wizard-from']").setValue("2026-10-01");
  await wrapper.get("[data-testid='wizard-to']").setValue("2026-10-31");
}

async function reachStep2(wrapper: VueWrapper): Promise<void> {
  await fillStep1(wrapper);
  await wrapper.get("[data-testid='wizard-next']").trigger("click");
  await flushPromises();
}

async function reachStep3(wrapper: VueWrapper): Promise<void> {
  await reachStep2(wrapper);
  await wrapper.get("[data-testid='wizard-step2-next']").trigger("click");
  await flushPromises();
}

async function reachStep4(wrapper: VueWrapper): Promise<void> {
  await reachStep3(wrapper);
  await wrapper.get("[data-testid='wizard-step3-next']").trigger("click");
  await flushPromises();
}

describe("launch wizard", { timeout: 30000 }, () => {
  it("keeps unconfigured objects out of the selector and validates every required field", async () => {
    useHandlers();
    const { wrapper } = await mountWizard();

    const options = wrapper
      .get("[data-testid='wizard-target']")
      .findAll("option")
      .map((option) => option.text());
    expect(options).toContain("deep-research");
    expect(options).not.toContain("Explore");
    await wrapper.findAll(".seg button")[1]!.trigger("click");
    await flushPromises();
    expect(
      wrapper
        .get("[data-testid='wizard-target']")
        .findAll("option")
        .map((option) => option.text()),
    ).toContain("Explore");

    await wrapper.get("[data-testid='wizard-next']").trigger("click");
    await flushPromises();

    expect(wrapper.find("[data-testid='wizard-target-error']").exists()).toBe(
      true,
    );
    expect(wrapper.find("[data-testid='wizard-version-error']").exists()).toBe(
      true,
    );
    expect(wrapper.get("[data-testid='wizard-from-error']").text()).toBe(
      "请选择开始时间",
    );
    expect(wrapper.get("[data-testid='wizard-to-error']").text()).toBe(
      "请选择结束时间",
    );
    expect(
      wrapper.get("[data-testid='wizard-target']").attributes("aria-invalid"),
    ).toBe("true");
  });

  it("fills the bad-case window from the three relative presets", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 10, 10, 12, 0, 0));
    try {
      useHandlers();
      const { wrapper } = await mountWizard();
      const from = () =>
        (wrapper.get("[data-testid='wizard-from']").element as HTMLInputElement)
          .value;
      const to = () =>
        (wrapper.get("[data-testid='wizard-to']").element as HTMLInputElement)
          .value;
      const pressed = (id: string) =>
        wrapper
          .get(`[data-testid='wizard-range-${id}']`)
          .attributes("aria-pressed");

      await wrapper.get("[data-testid='wizard-range-7']").trigger("click");
      expect(from()).toBe("2026-11-04");
      expect(to()).toBe("2026-11-10");
      expect(pressed("7")).toBe("true");
      expect(pressed("30")).toBe("false");

      await wrapper.get("[data-testid='wizard-range-30']").trigger("click");
      expect(from()).toBe("2026-10-12");
      expect(to()).toBe("2026-11-10");
      expect(pressed("30")).toBe("true");

      await wrapper.get("[data-testid='wizard-range-6m']").trigger("click");
      expect(from()).toBe("2026-05-10");
      expect(to()).toBe("2026-11-10");
      expect(pressed("6m")).toBe("true");

      await wrapper.get("[data-testid='wizard-to']").setValue("2026-11-09");
      expect(pressed("7")).toBe("false");
      expect(pressed("30")).toBe("false");
      expect(pressed("6m")).toBe("false");
      expect(from()).toBe("2026-05-10");
      expect(to()).toBe("2026-11-09");
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows a retryable error when the target catalog cannot be read", async () => {
    useHandlers({ catalogError: true });
    const { wrapper } = await mountWizard();

    expect(wrapper.get("[data-testid='wizard-catalog-error']").text()).toContain(
      "进化对象清单读取失败",
    );
    expect(
      wrapper.find("[data-testid='wizard-catalog-retry']").exists(),
    ).toBe(true);
  });

  it("shows a configure entry when the workspace has no enabled targets", async () => {
    useHandlers({ catalog: { skill: [], agent: [] } });
    const { wrapper, router } = await mountWizard();

    const empty = wrapper.get("[data-testid='wizard-config-empty']");
    expect(empty.text()).toContain("当前空间还没有启用的进化对象");
    await wrapper
      .get("[data-testid='wizard-target-config-link']")
      .trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.path).toContain(
      `/workspaces/${workspaceId}/evolution/targets`,
    );
  });

  it("prefills the focus case object and version and shows the lock hint", async () => {
    useHandlers();
    const { wrapper } = await mountWizard("case-focus");

    expect(wrapper.get("[data-testid='wizard-focus-case']").text()).toContain(
      "已锁定为关注对象",
    );
    expect(
      (wrapper.get("[data-testid='wizard-target']").element as HTMLSelectElement)
        .value,
    ).toBe("tgt-1");
    expect(
      (wrapper.get("[data-testid='wizard-version']").element as HTMLInputElement)
        .value,
    ).toBe("v1.9.0");
  });

  it("keeps a focus case's branch clue even when it is not a tag", async () => {
    useHandlers();
    server.use(
      http.get(`/api${ws}/bad-cases/case-focus`, () =>
        HttpResponse.json({ ...focusBadCase, objectVersion: "feature/foo" }),
      ),
    );
    const { wrapper } = await mountWizard("case-focus");

    expect(
      (wrapper.get("[data-testid='wizard-version']").element as HTMLInputElement)
        .value,
    ).toBe("feature/foo");
  });

  it("offers defaultRef and tags as suggestions while keeping a typed branch or commit ref", async () => {
    const sessionBodies: unknown[] = [];
    useHandlers();
    server.use(
      http.get(`${apiBase}/targets/tgt-1/versions`, () =>
        HttpResponse.json({
          versions: ["v2.0.0", "v1.9.0"],
          defaultRef: "main",
        }),
      ),
      http.post(`${apiBase}/preview/sessions`, async ({ request }) => {
        sessionBodies.push(await request.json());
        return HttpResponse.json(sessionPreview);
      }),
    );
    const { wrapper } = await mountWizard();
    await wrapper.get("[data-testid='wizard-target']").setValue("tgt-1");
    await flushPromises();

    const versionInput = wrapper.get("[data-testid='wizard-version']");
    expect((versionInput.element as HTMLInputElement).value).toBe("main");
    await versionInput.trigger("focus");
    const suggestions = wrapper
      .findAll("[data-testid='wizard-version-option']")
      .map((option) => option.get(".mono").text());
    expect(suggestions).toEqual(["main", "v2.0.0", "v1.9.0"]);

    await wrapper.findAll("[data-testid='wizard-version-option']")[1]!.trigger("click");
    expect((versionInput.element as HTMLInputElement).value).toBe("v2.0.0");

    await versionInput.setValue("a3f9c21");
    expect((versionInput.element as HTMLInputElement).value).toBe("a3f9c21");
    await versionInput.setValue("feature/foo");
    await wrapper.get("[data-testid='wizard-from']").setValue("2026-10-01");
    await wrapper.get("[data-testid='wizard-to']").setValue("2026-10-31");
    await wrapper.get("[data-testid='wizard-next']").trigger("click");
    await flushPromises();

    expect(sessionBodies).toHaveLength(1);
    expect(sessionBodies[0]).toMatchObject({ targetVersion: "feature/foo" });
  });

  it("rejects a malformed ref before calling the preview", async () => {
    useHandlers();
    const { wrapper } = await mountWizard();
    await wrapper.get("[data-testid='wizard-target']").setValue("tgt-1");
    await wrapper.get("[data-testid='wizard-version']").setValue("feature bad^ref");
    await wrapper.get("[data-testid='wizard-from']").setValue("2026-10-01");
    await wrapper.get("[data-testid='wizard-to']").setValue("2026-10-31");
    await wrapper.get("[data-testid='wizard-next']").trigger("click");
    await flushPromises();

    expect(wrapper.get("[data-testid='wizard-version-error']").text()).toContain(
      "版本不能包含空格",
    );
    expect(wrapper.find("[data-testid='wizard-session-table']").exists()).toBe(
      false,
    );
  });

  it("surfaces a server ref_not_found as a git existence error", async () => {
    useHandlers({
      sessions: () =>
        HttpResponse.json(
          {
            error: {
              code: "TARGET_CONTENT_UNRESOLVED",
              message: "target content could not be resolved to a body hash",
              details: {
                targetType: "skill",
                reason: "ref_not_found",
              },
            },
          },
          { status: 422 },
        ),
    });
    const { wrapper } = await mountWizard();
    await fillStep1(wrapper);
    await wrapper.get("[data-testid='wizard-next']").trigger("click");
    await flushPromises();

    expect(wrapper.get("[data-testid='wizard-version-error']").text()).toContain(
      "该版本在仓库中不存在",
    );
    expect(
      wrapper.get("[data-testid='wizard-next']").attributes("disabled"),
    ).toBeDefined();
  });

  it("walks the four steps with server summaries and lands on attribution preview", async () => {
    const sessionBodies: unknown[] = [];
    const potentialBodies: unknown[] = [];
    const attributionBodies: unknown[] = [];
    useHandlers();
    server.use(
      http.post(`${apiBase}/preview/sessions`, async ({ request }) => {
        sessionBodies.push(await request.json());
        return HttpResponse.json(sessionPreview);
      }),
      http.post(`${apiBase}/preview/potential`, async ({ request }) => {
        potentialBodies.push(await request.json());
        return HttpResponse.json(potentialPreview);
      }),
      http.post(`${apiBase}/preview/attribution`, async ({ request }) => {
        attributionBodies.push(await request.json());
        return HttpResponse.json(attributionPreview);
      }),
    );
    const { wrapper } = await mountWizard();

    await reachStep2(wrapper);
    expect(sessionBodies).toEqual([
      {
        targetType: "skill",
        targetName: "deep-research",
        targetVersion: "v2.0.0",
        from: "2026-10-01",
        to: "2026-10-31",
        page: 1,
        pageSize: 4,
      },
    ]);
    expect(wrapper.get("[data-testid='wizard-session-table']").text()).toContain(
      "研究 session",
    );
    expect(wrapper.get(".wz-stats").text()).toContain("关联");
    expect(
      wrapper.get("[data-testid='wizard-condition-revision']").text(),
    ).toBe(`revision ${resolvedRevision}`);

    await wrapper.get("[data-testid='wizard-step2-next']").trigger("click");
    await flushPromises();
    expect(potentialBodies).toEqual([
      {
        targetType: "skill",
        targetName: "deep-research",
        targetVersion: "v2.0.0",
        from: "2026-10-01",
        to: "2026-10-31",
        policy: { preset: "default" },
        page: 1,
        pageSize: 5,
      },
    ]);
    const table = wrapper.get("[data-testid='wizard-potential-table']").text();
    expect(table).toContain("case…0001");
    expect(table).toContain("self 上报");
    expect(table).toContain("触发点顺序待轨迹时间戳重放");
    expect(table).toContain("事件锚点");
    expect(
      wrapper.get("[data-anchor-source='post_process']").text(),
    ).toBe("后处理上报");
    expect(table).not.toContain("2147483647");
    expect(
      wrapper.get("[data-testid='wizard-condition-revision']").text(),
    ).toBe(`revision ${resolvedRevision}`);

    await wrapper.get("[data-testid='wizard-step3-next']").trigger("click");
    await flushPromises();
    expect(attributionBodies).toEqual([
      {
        targetType: "skill",
        targetName: "deep-research",
        targetVersion: "v2.0.0",
        from: "2026-10-01",
        to: "2026-10-31",
        policy: { preset: "default" },
        cacheEnabled: true,
      },
    ]);
    const stats = wrapper.get("[data-testid='wizard-attribution-stats']").text();
    expect(stats).toContain("2");
    expect(stats).toContain("复用缓存");
    expect(stats).toContain("0本次新增归因");
    expect(wrapper.get("[data-testid='wizard-effective-skill']").text()).toContain(
      "attribute-badcases · 1 份",
    );
    expect(
      wrapper.get("[data-testid='wizard-condition-revision']").text(),
    ).toBe(`revision ${resolvedRevision}`);
  });

  it("renders a clamped short Session label with the full prompt in the tooltip", async () => {
    const longTitle =
      "You are an autonomous software engineer working in the repository at /testbed. " +
      "Solve the issue by editing the repository and running the test suite.";
    useHandlers({
      sessions: () =>
        HttpResponse.json({
          ...sessionPreview,
          items: [
            {
              sessionId: "session-long-prompt",
              short: "SWE-bench 会话",
              title: longTitle,
              objectTriggerAt: "2026-10-20T09:00:00+08:00",
              badCaseCount: 2,
            },
          ],
          total: 1,
          summary: {
            reported: 1,
            associated: 1,
            skipped: 0,
            versionUnresolved: 0,
            pending: 0,
          },
        }),
    });
    const { wrapper } = await mountWizard();
    await reachStep2(wrapper);

    const title = wrapper.get("[data-testid='wizard-session-title']");
    expect(title.text()).toBe("SWE-bench 会话");
    expect(title.attributes("title")).toBe(longTitle);
    expect(title.classes()).toContain("wz-session-title");
    expect(
      wrapper.get("[data-testid='wizard-session-table']").classes(),
    ).toContain("wz-session-table");
    expect(
      wrapper.get("[data-testid='wizard-session-table']").findAll("th"),
    ).toHaveLength(4);
    expect(
      wrapper.get("[data-testid='wizard-session-table']").text(),
    ).toContain("#sess…ompt");
  });

  it("shows the resolved version → revision in Step 1 and clears it on version change", async () => {
    useHandlers();
    const { wrapper } = await mountWizard();
    await reachStep2(wrapper);
    await wrapper.get("[data-testid='wizard-back']").trigger("click");
    await flushPromises();

    expect(
      wrapper.get("[data-testid='wizard-target-revision']").text(),
    ).toBe(`v2.0.0 → ${resolvedRevision}`);
    expect(
      wrapper.get("[data-testid='wizard-target-revision']").attributes("title"),
    ).toBe(resolvedRevision);

    await wrapper.get("[data-testid='wizard-version']").setValue("v1.9.0");
    await flushPromises();

    expect(
      wrapper.find("[data-testid='wizard-target-revision']").exists(),
    ).toBe(false);
    expect(wrapper.text()).not.toContain(resolvedRevision);
  });

  it("shows explicit unresolved revision copy when the preview returns null", async () => {
    useHandlers({
      sessions: () =>
        HttpResponse.json({ ...sessionPreview, targetRevision: null }),
    });
    const { wrapper } = await mountWizard();
    await reachStep2(wrapper);

    expect(
      wrapper.get("[data-testid='wizard-condition-revision']").text(),
    ).toBe("revision 未解析");
    await wrapper.get("[data-testid='wizard-back']").trigger("click");
    await flushPromises();

    expect(
      wrapper.get("[data-testid='wizard-target-revision-unresolved']").text(),
    ).toContain("未解析到 revision");
    expect(wrapper.text()).not.toContain("digest:");
    expect(
      wrapper.find("[data-testid='wizard-target-revision']").exists(),
    ).toBe(false);
  });

  it("explains the missing agent and keeps existing reports available", async () => {
    useHandlers({ attribution: () => HttpResponse.json({ ...attributionPreview, canRecompute: false }) });
    const { wrapper } = await mountWizard();
    await reachStep4(wrapper);
    expect(wrapper.get("[data-testid='wizard-cache']").attributes("disabled")).toBeDefined();
    expect(wrapper.find("select[aria-label='本次重算使用的归因 Skill']").exists()).toBe(false);
    expect(wrapper.text()).toContain("归因运行时不可用，可以复用已有报告");
    expect(wrapper.get("[data-testid='wizard-cluster']").attributes("disabled")).toBeUndefined();
  });

  it.each([true, false])("can generate reports for an unbound production target with cache=%s", async (cacheEnabled) => {
    const submitted: unknown[] = [];
    useHandlers({
      attribution: () => HttpResponse.json({
        ...attributionPreview,
        usesBoundSkill: false,
        canRecompute: false,
        summary: { potential: 2, reused: 0, fresh: 2, missing: 0, bySkill: {}, nonTargetKnown: 0 },
      }),
    });
    server.use(http.post(`${apiBase}/runs`, async ({ request }) => {
      submitted.push(await request.json());
      return HttpResponse.json({ runId: "new-run", jobId: "new-job", status: "preparing" }, { status: 202 });
    }));
    const { wrapper } = await mountWizard();
    await reachStep4(wrapper);
    expect(wrapper.get("[data-testid='wizard-cache']").attributes("disabled")).toBeUndefined();
    if (!cacheEnabled) {
      await wrapper.get("[data-testid='wizard-cache']").setValue(false);
      await flushPromises();
    }
    expect(wrapper.find("select[aria-label='本次重算使用的归因 Skill']").exists()).toBe(false);
    const start = wrapper.get("[data-testid='wizard-start']");
    expect(start.attributes("disabled")).toBeUndefined();
    await start.trigger("click");
    await flushPromises();
    expect(submitted[0]).toMatchObject({ cacheEnabled });
    expect(submitted[0]).not.toHaveProperty("attributionPackageId");
    wrapper.unmount();
  });

  it("keeps cached launch unavailable when a bound target has no reports", async () => {
    useHandlers({ attribution: () => HttpResponse.json({
      ...attributionPreview,
      summary: { potential: 2, reused: 0, fresh: 0, missing: 2, bySkill: {}, nonTargetKnown: 0 },
    }) });
    const { wrapper } = await mountWizard();
    await reachStep4(wrapper);
    expect(wrapper.get("[data-testid='wizard-start']").attributes("disabled")).toBeDefined();
    expect(wrapper.get("[data-testid='wizard-effective-skill']").text()).toContain("本次跳过");
    wrapper.unmount();
  });

  it("re-requests the attribution preview when the cache switch changes", async () => {
    const bodies: unknown[] = [];
    useHandlers();
    server.use(
      http.post(`${apiBase}/preview/attribution`, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(attributionPreview);
      }),
    );
    const { wrapper } = await mountWizard();
    await reachStep4(wrapper);

    await wrapper.get("[data-testid='wizard-cache']").setValue(false);
    await flushPromises();

    expect(bodies).toHaveLength(2);
    expect(bodies[1]).toMatchObject({ cacheEnabled: false });
  });

  it("launches a full run with the policy and cache snapshot", async () => {
    const bodies: unknown[] = [];
    useHandlers();
    server.use(
      http.post(`${apiBase}/runs`, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(
          { runId: "run-full", jobId: "job-full", status: "preparing" },
          { status: 202 },
        );
      }),
    );
    const { wrapper } = await mountWizard();
    await reachStep4(wrapper);

    await wrapper.get("[data-testid='wizard-start']").trigger("click");
    await flushPromises();

    expect(bodies).toEqual([
      {
        targetType: "skill",
        targetName: "deep-research",
        targetVersion: "v2.0.0",
        from: "2026-10-01",
        to: "2026-10-31",
        mode: "full",
        policy: { preset: "default" },
        cacheEnabled: true,
        page: 1,
        pageSize: 5,
      },
    ]);
    expect(wrapper.emitted("launched")).toEqual([["full", "run-full"]]);
  });

  it("launches a cluster-only preview with the dedicated mode", async () => {
    const bodies: unknown[] = [];
    useHandlers();
    server.use(
      http.post(`${apiBase}/cluster-previews`, async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json(
          {
            runId: "run-cluster",
            jobId: "job-cluster",
            status: "preparing",
          },
          { status: 202 },
        );
      }),
    );
    const { wrapper } = await mountWizard();
    await reachStep4(wrapper);

    await wrapper.get("[data-testid='wizard-cluster']").trigger("click");
    await flushPromises();

    expect(bodies).toHaveLength(1);
    expect(bodies[0]).toMatchObject({ mode: "cluster_only" });
    expect(wrapper.emitted("launched")).toEqual([
      ["cluster_only", "run-cluster"],
    ]);
  });

  it("renders the empty Session state and disables forward navigation", async () => {
    useHandlers({
      sessions: () =>
        HttpResponse.json(
          {
            error: {
              code: "NO_ASSOCIATED_SESSIONS",
              message: "no session is associated",
              details: {
                summary: {
                  reported: 6,
                  associated: 0,
                  skipped: 6,
                  versionUnresolved: 0,
                  pending: 0,
                },
              },
            },
          },
          { status: 409 },
        ),
    });
    const { wrapper } = await mountWizard();
    await reachStep2(wrapper);

    expect(wrapper.get("[data-testid='wizard-session-empty']").text()).toContain(
      "没有对象出现过的 Session",
    );
    expect(
      wrapper
        .get("[data-testid='wizard-step2-next']")
        .attributes("disabled"),
    ).toBeDefined();
  });

  it("renders the empty potential state and disables forward navigation", async () => {
    useHandlers({
      potential: () =>
        HttpResponse.json(
          {
            error: {
              code: "NO_POTENTIAL_MATCHED",
              message: "no bad case matches",
            },
          },
          { status: 409 },
        ),
    });
    const { wrapper } = await mountWizard();
    await reachStep3(wrapper);

    expect(
      wrapper.get("[data-testid='wizard-potential-empty']").text(),
    ).toContain("当前策略没有命中潜在 bad case");
    expect(
      wrapper
        .get("[data-testid='wizard-step3-next']")
        .attributes("disabled"),
    ).toBeDefined();
  });

  it("blocks a custom policy with no matching rule and sends the checked rule union", async () => {
    const sessionBodies: unknown[] = [];
    const potentialBodies: unknown[] = [];
    useHandlers();
    server.use(
      http.post(`${apiBase}/preview/sessions`, async ({ request }) => {
        sessionBodies.push(await request.json());
        return HttpResponse.json(sessionPreview);
      }),
      http.post(`${apiBase}/preview/potential`, async ({ request }) => {
        potentialBodies.push(await request.json());
        return HttpResponse.json(potentialPreview);
      }),
    );
    const { wrapper } = await mountWizard();

    await wrapper.get("[data-testid='wizard-policy-custom']").setValue();
    await wrapper.get("[data-testid='wizard-rule-self']").setValue(false);
    await wrapper.get("[data-testid='wizard-rule-after']").setValue(false);
    await fillStep1(wrapper);
    await wrapper.get("[data-testid='wizard-next']").trigger("click");
    await flushPromises();

    expect(wrapper.find("[data-testid='wizard-policy-error']").exists()).toBe(
      true,
    );
    expect(sessionBodies).toHaveLength(0);

    await wrapper.get("[data-testid='wizard-rule-after']").setValue(true);
    await wrapper.get("[data-testid='wizard-next']").trigger("click");
    await flushPromises();
    expect(sessionBodies).toHaveLength(1);
    expect(sessionBodies[0]).not.toHaveProperty("policy");

    await wrapper.get("[data-testid='wizard-step2-next']").trigger("click");
    await flushPromises();
    expect(potentialBodies).toHaveLength(1);
    expect(potentialBodies[0]).toMatchObject({
      policy: {
        preset: "custom",
        includeSelfReport: false,
        includeAfterObject: true,
        sameObjectOnly: false,
      },
    });
    expect(
      wrapper.find("[data-testid='wizard-potential-table']").exists(),
    ).toBe(true);
  });

  it("requests another Session page without recomputing the condition", async () => {
    const bodies: unknown[] = [];
    useHandlers();
    server.use(
      http.post(`${apiBase}/preview/sessions`, async ({ request }) => {
        const body = (await request.json()) as { page: number };
        bodies.push(body);
        return HttpResponse.json({
          ...sessionPreview,
          page: body.page,
          total: 6,
        });
      }),
    );
    const { wrapper } = await mountWizard();
    await reachStep2(wrapper);

    await wrapper.get("[data-testid='wizard-session-next']").trigger("click");
    await flushPromises();

    expect(bodies).toEqual([
      expect.objectContaining({ page: 1, pageSize: 4 }),
      expect.objectContaining({ page: 2, pageSize: 4 }),
    ]);
    expect(wrapper.get(".pager-info").text()).toContain("2");
  });

  it("requests another potential page while keeping the policy", async () => {
    const bodies: unknown[] = [];
    useHandlers();
    server.use(
      http.post(`${apiBase}/preview/potential`, async ({ request }) => {
        const body = (await request.json()) as { page: number };
        bodies.push(body);
        return HttpResponse.json({
          ...potentialPreview,
          page: body.page,
          total: 7,
        });
      }),
    );
    const { wrapper } = await mountWizard();
    await reachStep3(wrapper);

    await wrapper.get("[data-testid='wizard-potential-next']").trigger("click");
    await flushPromises();

    expect(bodies).toEqual([
      expect.objectContaining({ page: 1, pageSize: 5 }),
      expect.objectContaining({ page: 2, pageSize: 5 }),
    ]);
  });

  it("keeps step 1 with an inline error when the Session preview fails", async () => {
    useHandlers({
      sessions: () =>
        HttpResponse.json(
          {
            error: {
              code: "TARGET_NOT_CONFIGURED",
              message: "target is not configured or enabled",
            },
          },
          { status: 409 },
        ),
    });
    const { wrapper } = await mountWizard();
    await reachStep2(wrapper);

    expect(wrapper.find("[data-testid='wizard-error']").exists()).toBe(true);
    expect(wrapper.find("[data-testid='wizard-session-table']").exists()).toBe(
      false,
    );
    expect(wrapper.find("[data-testid='wizard-next']").exists()).toBe(true);
  });

  it("turns TARGET_CONTENT_UNRESOLVED into an actionable version error", async () => {
    let attempts = 0;
    useHandlers({
      sessions: () => {
        attempts += 1;
        return attempts === 1
          ? HttpResponse.json(
              {
                error: {
                  code: "TARGET_CONTENT_UNRESOLVED",
                  message: "target content could not be resolved to a body hash",
                  details: {
                    targetType: "skill",
                    reason: "content_not_found",
                  },
                },
              },
              { status: 422 },
            )
          : HttpResponse.json(sessionPreview);
      },
    });
    const { wrapper } = await mountWizard();
    await fillStep1(wrapper);
    await wrapper.get("[data-testid='wizard-next']").trigger("click");
    await flushPromises();

    const versionError = wrapper.get("[data-testid='wizard-version-error']");
    expect(versionError.text()).toContain("找不到目标文件");
    expect(versionError.text()).not.toContain("could not be resolved");
    expect(
      wrapper.get("[data-testid='wizard-next']").attributes("disabled"),
    ).toBeDefined();
    expect(wrapper.find("[data-testid='wizard-session-empty']").exists()).toBe(
      false,
    );

    await wrapper.get("[data-testid='wizard-content-retry']").trigger("click");
    await flushPromises();

    expect(
      wrapper.get("[data-testid='wizard-session-table']").text(),
    ).toContain("研究 session");
  });

  it("shows a live progress card and locks the form while the Session preview is pending", async () => {
    let release!: () => void;
    useHandlers({
      sessions: () =>
        new Promise<Response>((resolve) => {
          release = () => resolve(HttpResponse.json(sessionPreview));
        }),
    });
    const { wrapper } = await mountWizard();
    await fillStep1(wrapper);
    await wrapper.get("[data-testid='wizard-next']").trigger("click");
    await flushPromises();

    const card = wrapper.get("[data-testid='wizard-progress']");
    expect(card.attributes("role")).toBe("status");
    expect(card.attributes("aria-live")).toBeUndefined();
    expect(card.text()).toContain("正在准备第 2 步 · 读取目标版本");
    const elapsed = wrapper.get("[data-testid='wizard-elapsed']");
    expect(elapsed.text()).toMatch(/^已等待 \d+ 秒$/);
    expect(elapsed.attributes("aria-hidden")).toBe("true");
    const stages = wrapper.findAll("[data-testid='wizard-progress-stage']");
    expect(stages).toHaveLength(2);
    expect(stages[0]!.text()).toContain("读取目标版本");
    expect(stages[0]!.text()).toContain("进行中");
    expect(stages[0]!.text()).toContain("SKILL.md / AGENT.md");
    expect(stages[1]!.text()).toContain("关联 Session");
    expect(stages[1]!.text()).toContain("等待");
    expect(stages[1]!.text()).toContain("2026-10-01 ~ 2026-10-31");
    const next = wrapper.get("[data-testid='wizard-next']");
    expect(next.attributes("disabled")).toBeDefined();
    expect(next.text()).toContain("正在读取目标版本");
    expect(next.find(".wz-spinner").exists()).toBe(true);
    expect(wrapper.find("[data-testid='wizard-cancel-wait']").exists()).toBe(
      true,
    );
    const form = wrapper.get("[data-testid='wizard-form']");
    expect(form.attributes("inert")).toBeDefined();
    expect(form.classes()).toContain("locked");
    expect(
      (wrapper.get("[data-testid='wizard-version']").element as HTMLInputElement)
        .value,
    ).toBe("v2.0.0");

    release();
    await flushPromises();

    expect(wrapper.find("[data-testid='wizard-progress']").exists()).toBe(false);
    expect(
      wrapper.get("[data-testid='wizard-session-table']").text(),
    ).toContain("研究 session");
    expect(
      wrapper.get("[data-testid='wizard-form']").attributes("inert"),
    ).toBeUndefined();
    expect(
      wrapper.find("[data-testid='wizard-step2-next']").exists(),
    ).toBe(true);
  });

  it("shows the timeout card and retries into step 2", async () => {
    let attempts = 0;
    let releaseRetry!: () => void;
    useHandlers({
      sessions: () => {
        attempts += 1;
        if (attempts === 1) {
          return HttpResponse.json(contentTimeoutError, { status: 422 });
        }
        return new Promise<Response>((resolve) => {
          releaseRetry = () => resolve(HttpResponse.json(sessionPreview));
        });
      },
    });
    const { wrapper } = await mountWizard();
    await fillStep1(wrapper);
    await wrapper.get("[data-testid='wizard-next']").trigger("click");
    await flushPromises();

    const card = wrapper.get("[data-testid='wizard-progress-failed']");
    expect(card.attributes("role")).toBe("alert");
    expect(card.text()).toContain("读取目标版本超时");
    expect(card.text()).toContain("读取目标文件超时");
    expect(card.text()).toContain("不是 Session 数据为空");
    expect(wrapper.get("[data-testid='wizard-elapsed']").text()).toContain(
      "已等待",
    );
    expect(
      wrapper.get("[data-testid='wizard-version']").classes(),
    ).toContain("input-error");
    expect(
      wrapper.get("[data-testid='wizard-version']").attributes("aria-describedby"),
    ).toBe("wizard-content-error");
    expect(wrapper.find("#wizard-content-error").exists()).toBe(true);
    expect(
      wrapper.find("[data-testid='wizard-progress-retry']").exists(),
    ).toBe(true);
    expect(wrapper.find("[data-testid='wizard-content-back']").exists()).toBe(
      true,
    );
    expect(
      wrapper.get("[data-testid='wizard-form']").attributes("inert"),
    ).toBeUndefined();

    await wrapper.get("[data-testid='wizard-progress-retry']").trigger("click");
    await flushPromises();

    expect(
      wrapper.find("[data-testid='wizard-progress-failed']").exists(),
    ).toBe(false);
    expect(wrapper.get("[data-testid='wizard-progress']").text()).toContain(
      "正在准备第 2 步 · 读取目标版本",
    );
    expect(wrapper.find("[data-testid='wizard-cancel-wait']").exists()).toBe(
      true,
    );

    releaseRetry();
    await flushPromises();

    expect(
      wrapper.get("[data-testid='wizard-session-table']").text(),
    ).toContain("研究 session");
    expect(wrapper.find("[data-testid='wizard-progress']").exists()).toBe(false);
  });

  it("keeps the timeout card on the step-1 target stage when a later preview times out", async () => {
    useHandlers({
      potential: () => HttpResponse.json(contentTimeoutError, { status: 422 }),
    });
    const { wrapper } = await mountWizard();
    await reachStep2(wrapper);
    await wrapper.get("[data-testid='wizard-step2-next']").trigger("click");
    await flushPromises();

    const card = wrapper.get("[data-testid='wizard-progress-failed']");
    expect(card.text()).toContain("读取目标版本超时");
    expect(card.text()).not.toContain("筛选潜在 bad case超时");
    expect(wrapper.findAll("[data-testid='wizard-progress-stage']")).toHaveLength(
      2,
    );
    expect(wrapper.find("[data-testid='wizard-session-table']").exists()).toBe(
      false,
    );
    expect(wrapper.find("[data-testid='wizard-next']").exists()).toBe(true);
  });

  it("dismisses the timeout card with 返回修改条件 and keeps the form values", async () => {
    useHandlers({
      sessions: () => HttpResponse.json(contentTimeoutError, { status: 422 }),
    });
    const { wrapper } = await mountWizard();
    await fillStep1(wrapper);
    await wrapper.get("[data-testid='wizard-next']").trigger("click");
    await flushPromises();

    expect(
      wrapper.find("[data-testid='wizard-progress-failed']").exists(),
    ).toBe(true);
    await wrapper.get("[data-testid='wizard-content-back']").trigger("click");
    await flushPromises();

    expect(
      wrapper.find("[data-testid='wizard-progress-failed']").exists(),
    ).toBe(false);
    expect(wrapper.find("[data-testid='wizard-progress']").exists()).toBe(false);
    expect(
      wrapper.get("[data-testid='wizard-form']").attributes("inert"),
    ).toBeUndefined();
    expect(
      (wrapper.get("[data-testid='wizard-version']").element as HTMLInputElement)
        .value,
    ).toBe("v2.0.0");
    expect(
      (wrapper.get("[data-testid='wizard-from']").element as HTMLInputElement)
        .value,
    ).toBe("2026-10-01");
    expect(
      wrapper.get("[data-testid='wizard-next']").attributes("disabled"),
    ).toBeUndefined();
  });

  it("cancels a pending preview without advancing on the late response", async () => {
    let release!: () => void;
    useHandlers({
      sessions: () =>
        new Promise<Response>((resolve) => {
          release = () => resolve(HttpResponse.json(sessionPreview));
        }),
    });
    const { wrapper } = await mountWizard();
    await fillStep1(wrapper);
    await wrapper.get("[data-testid='wizard-next']").trigger("click");
    await flushPromises();

    expect(wrapper.find("[data-testid='wizard-progress']").exists()).toBe(true);
    await wrapper.get("[data-testid='wizard-cancel-wait']").trigger("click");
    await flushPromises();

    expect(wrapper.find("[data-testid='wizard-progress']").exists()).toBe(false);
    expect(
      wrapper.get("[data-testid='wizard-form']").attributes("inert"),
    ).toBeUndefined();
    const next = wrapper.get("[data-testid='wizard-next']");
    expect(next.attributes("disabled")).toBeUndefined();
    expect(next.text()).toContain("下一步：关联 Session");

    release();
    await flushPromises();
    await flushPromises();

    expect(wrapper.find("[data-testid='wizard-session-table']").exists()).toBe(
      false,
    );
    expect(wrapper.find("[data-testid='wizard-step2-next']").exists()).toBe(
      false,
    );
    expect(wrapper.find("[data-testid='wizard-next']").exists()).toBe(true);
    expect(
      (wrapper.get("[data-testid='wizard-version']").element as HTMLInputElement)
        .value,
    ).toBe("v2.0.0");
  });

  it("advances the elapsed timer and formats a minute-long wait", async () => {
    vi.useFakeTimers();
    const clearIntervalSpy = vi.spyOn(globalThis, "clearInterval");
    try {
      let release!: () => void;
      useHandlers({
        sessions: () =>
          new Promise<Response>((resolve) => {
            release = () => resolve(HttpResponse.json(sessionPreview));
          }),
      });
      const { wrapper } = await mountWizard();
      await fillStep1(wrapper);
      await wrapper.get("[data-testid='wizard-next']").trigger("click");
      await flushPromises();

      expect(wrapper.get("[data-testid='wizard-elapsed']").text()).toBe(
        "已等待 0 秒",
      );
      await vi.advanceTimersByTimeAsync(1_000);
      await flushPromises();
      expect(wrapper.get("[data-testid='wizard-elapsed']").text()).toBe(
        "已等待 1 秒",
      );
      await vi.advanceTimersByTimeAsync(59_000);
      await flushPromises();
      expect(wrapper.get("[data-testid='wizard-elapsed']").text()).toBe(
        "已等待 1 分 00 秒",
      );

      release();
      await flushPromises();
      expect(wrapper.find("[data-testid='wizard-progress']").exists()).toBe(
        false,
      );
      expect(clearIntervalSpy).toHaveBeenCalled();
      await vi.advanceTimersByTimeAsync(1_000);
      await flushPromises();
      expect(wrapper.find("[data-testid='wizard-progress']").exists()).toBe(
        false,
      );
    } finally {
      clearIntervalSpy.mockRestore();
      vi.useRealTimers();
    }
  });

  it("keeps a new preview running when the cancelled request resolves late", async () => {
    const releases: Array<() => void> = [];
    useHandlers({
      sessions: () =>
        new Promise<Response>((resolve) => {
          releases.push(() => resolve(HttpResponse.json(sessionPreview)));
        }),
    });
    const { wrapper } = await mountWizard();
    await fillStep1(wrapper);
    await wrapper.get("[data-testid='wizard-next']").trigger("click");
    await flushPromises();

    expect(wrapper.find("[data-testid='wizard-progress']").exists()).toBe(true);
    await wrapper.get("[data-testid='wizard-cancel-wait']").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-testid='wizard-progress']").exists()).toBe(false);

    await wrapper.get("[data-testid='wizard-next']").trigger("click");
    await flushPromises();
    expect(wrapper.find("[data-testid='wizard-progress']").exists()).toBe(true);
    expect(releases).toHaveLength(2);

    releases[0]!();
    await flushPromises();
    expect(wrapper.find("[data-testid='wizard-progress']").exists()).toBe(true);
    expect(wrapper.find("[data-testid='wizard-session-table']").exists()).toBe(
      false,
    );
    expect(wrapper.find("[data-testid='wizard-step2-next']").exists()).toBe(
      false,
    );

    releases[1]!();
    await flushPromises();
    expect(wrapper.find("[data-testid='wizard-progress']").exists()).toBe(false);
    expect(
      wrapper.get("[data-testid='wizard-session-table']").text(),
    ).toContain("研究 session");
  });

  it("shows the stage-aware progress card while the potential preview is pending", async () => {
    let release!: () => void;
    useHandlers();
    server.use(
      http.post(
        `${apiBase}/preview/potential`,
        () =>
          new Promise<Response>((resolve) => {
            release = () => resolve(HttpResponse.json(potentialPreview));
          }),
      ),
    );
    const { wrapper } = await mountWizard();
    await reachStep2(wrapper);
    await wrapper.get("[data-testid='wizard-step2-next']").trigger("click");
    await flushPromises();

    expect(wrapper.get("[data-testid='wizard-progress']").text()).toContain(
      "正在准备第 3 步 · 筛选潜在 bad case",
    );
    expect(wrapper.get("[data-testid='wizard-elapsed']").text()).toMatch(
      /^已等待 \d+ 秒$/,
    );
    expect(
      wrapper.findAll("[data-testid='wizard-progress-stage']"),
    ).toHaveLength(1);
    expect(
      wrapper.get("[data-testid='wizard-step2-next']").text(),
    ).toContain("正在筛选潜在 bad case");
    expect(wrapper.find("[data-testid='wizard-back']").exists()).toBe(false);

    release();
    await flushPromises();

    expect(
      wrapper.find("[data-testid='wizard-potential-table']").exists(),
    ).toBe(true);
  });

  it("closes from the dialog, the close button, and Escape", async () => {
    useHandlers();
    const { wrapper } = await mountWizard();

    const dialog = wrapper.get("[data-testid='launch-wizard']");
    expect(dialog.attributes("role")).toBe("dialog");
    expect(dialog.attributes("aria-modal")).toBe("true");
    expect(wrapper.get("h2").text()).toBe("启动自进化");

    await wrapper.get("[aria-label='关闭向导']").trigger("click");
    expect(wrapper.emitted("close")).toHaveLength(1);

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    await flushPromises();
    expect(wrapper.emitted("close")).toHaveLength(2);
  });
});
