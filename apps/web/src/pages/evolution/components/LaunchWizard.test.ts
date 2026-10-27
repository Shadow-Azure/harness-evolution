// @vitest-environment jsdom

import type { ProbeQueryResult } from "@harness/contracts";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";
import { http, HttpResponse } from "msw";

import { server } from "../../../test/server";
import LaunchWizard from "./LaunchWizard.vue";

const wrappers: VueWrapper[] = [];

const preview: ProbeQueryResult = {
  summary: {
    sessions: 2,
    badCases: 3,
    analyzed: 2,
    unanalyzed: 1,
    probes: 2,
    usedProbes: 2,
    byAttributeType: { model: 0, prompt: 1, error: 1, nonIssue: 0 },
  },
  items: [
    {
      probeId: "probe-synthetic-0001",
      sessionId: "session-1",
      sessionTitle: "研究 session",
      model: "glm-5.3",
      probeType: "skill",
      probeObject: "deep-research",
      objectVersion: "v2.0.0",
      attributeType: "error",
      description: "检索索引读取失败",
      sourceBadCaseIds: ["case-1"],
    },
  ],
  total: 1,
  page: 1,
  pageSize: 8,
};

async function mountWizard() {
  const pinia = createPinia();
  setActivePinia(pinia);
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/:pathMatch(.*)*", component: { template: "<div />" } }],
  });
  await router.push("/");
  await router.isReady();
  const wrapper = mount(LaunchWizard, {
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
  return wrapper;
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount();
  server.resetHandlers();
});
afterAll(() => server.close());

function useCatalogHandlers(): void {
  server.use(
    http.get("/api/catalogs/targets", () =>
      HttpResponse.json({
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
        agent: [],
      })),
    http.get("/api/catalogs/models", () =>
      HttpResponse.json({
        items: [{ model: "glm-5.3", sessionCount: 12, agentCount: 20 }],
      })),
    http.get("/api/evolution/targets/tgt-1/versions", () =>
      HttpResponse.json({ versions: ["v2.0.0", "v1.9.0"], defaultRef: "v2.0.0" })),
  );
}

describe("launch wizard", { timeout: 30000 }, () => {
  it("keeps unconfigured objects out of the candidate selector", async () => {
    useCatalogHandlers();
    const wrapper = await mountWizard();

    const options = wrapper
      .get("[data-testid='wizard-target']")
      .findAll("option")
      .map((option) => option.text());
    expect(options).toEqual(["选择对象", "deep-research"]);
    expect(wrapper.get("[data-testid='wizard-next']").attributes("disabled")).toBeDefined();
  });

  it("queries hits on the next step and shows the prototype statistics frame", async () => {
    useCatalogHandlers();
    server.use(
      http.post("/api/evolution/probes/query", () => HttpResponse.json(preview)),
    );
    const wrapper = await mountWizard();

    await wrapper.get("[data-testid='wizard-target']").setValue("tgt-1");
    await flushPromises();
    await wrapper.get("[data-testid='wizard-version']").setValue("v2.0.0");
    await wrapper.get("[data-testid='wizard-next']").trigger("click");
    await flushPromises();

    expect(wrapper.get(".wz-condstrip").text()).toContain("skill:deep-research@v2.0.0");
    expect(wrapper.get(".wz-stats").text()).toContain("「是问题」进入聚类");
    expect(wrapper.get("table.rep").text()).toContain("probe-s".slice(0, 8));
    expect(wrapper.text()).toContain("等待外部归因");
  });

  it("conflicts when no probe matches and stays on step 1", async () => {
    useCatalogHandlers();
    server.use(
      http.post("/api/evolution/probes/query", () =>
        HttpResponse.json(
          { error: { code: "NO_PROBES_MATCHED", message: "no hits", details: {} } },
          { status: 409 },
        ),
      ),
    );
    const wrapper = await mountWizard();

    await wrapper.get("[data-testid='wizard-target']").setValue("tgt-1");
    await flushPromises();
    await wrapper.get("[data-testid='wizard-version']").setValue("v2.0.0");
    await wrapper.get("[data-testid='wizard-next']").trigger("click");
    await flushPromises();

    expect(wrapper.find("[data-testid='wizard-cluster']").exists()).toBe(false);
    expect(wrapper.find(".wizard-error").exists()).toBe(true);
  });

  it("launches a cluster-only run and reports the accepted run id", async () => {
    useCatalogHandlers();
    const bodies: Record<string, unknown>[] = [];
    server.use(
      http.post("/api/evolution/probes/query", () => HttpResponse.json(preview)),
      http.post("/api/evolution/cluster-previews", async ({ request }) => {
        bodies.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json({
          runId: "evo-preview-1",
          jobId: "job-1",
          status: "preparing",
        });
      }),
    );
    const wrapper = await mountWizard();

    await wrapper.get("[data-testid='wizard-target']").setValue("tgt-1");
    await flushPromises();
    await wrapper.get("[data-testid='wizard-version']").setValue("v2.0.0");
    await wrapper.get("[data-testid='wizard-next']").trigger("click");
    await flushPromises();
    await wrapper.get("[data-testid='wizard-cluster']").trigger("click");
    await flushPromises();

    expect(bodies[0]).toMatchObject({ mode: "cluster_only", targetName: "deep-research" });
    expect(wrapper.emitted("launched")).toEqual([["cluster_only", "evo-preview-1"]]);
  });

  it("launches a full run for the primary action", async () => {
    useCatalogHandlers();
    server.use(
      http.post("/api/evolution/probes/query", () => HttpResponse.json(preview)),
      http.post("/api/evolution/runs", () =>
        HttpResponse.json(
          { runId: "evo-full-1", jobId: "job-2", status: "preparing" },
          { status: 202 },
        ),
      ),
    );
    const wrapper = await mountWizard();

    await wrapper.get("[data-testid='wizard-target']").setValue("tgt-1");
    await flushPromises();
    await wrapper.get("[data-testid='wizard-version']").setValue("v2.0.0");
    await wrapper.get("[data-testid='wizard-next']").trigger("click");
    await flushPromises();
    await wrapper.get("[data-testid='wizard-start']").trigger("click");
    await flushPromises();

    expect(wrapper.emitted("launched")).toEqual([["full", "evo-full-1"]]);
  });
});
