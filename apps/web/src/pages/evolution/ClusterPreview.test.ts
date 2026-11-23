// @vitest-environment jsdom

import { flushPromises, mount } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { http, HttpResponse } from "msw";
import { createPinia, setActivePinia } from "pinia";
import {
  afterAll,
  afterEach,
  beforeAll,
  describe,
  expect,
  it,
} from "vitest";

import { createAppRouter } from "../../router";
import { signInWithWorkspace } from "../../test/auth";
import { server } from "../../test/server";
import ClusterPreview from "./ClusterPreview.vue";

const workspaceId = "ws-test";
const runId = "run-cluster";
const runPath = `/workspaces/${workspaceId}/evolution/cluster/${runId}`;
const detailPath = `/api/workspaces/${workspaceId}/evolution/runs/${runId}`;
const rangePath = `${detailPath}/steps/range`;
const clustersPath = `${detailPath}/steps/clusters`;
const attributionPath = `${detailPath}/steps/attribution`;
const launchPath = `/api/workspaces/${workspaceId}/evolution/runs`;

type RunStatus = "preparing" | "running" | "completed" | "failed";

function runDetail(status: RunStatus) {
  const completed = status === "completed";
  return {
    runId,
    title: "cluster only run",
    mode: "cluster_only",
    target: { type: "skill", name: "synthetic-review", version: "synthetic-1" },
    window: { from: "2026-10-01", to: "2026-10-31" },
    models: ["glm-5.3"],
    policy: { preset: "default" },
    cacheEnabled: false,
    createdBy: "Administrator",
    createdAt: "2026-11-17T08:00:00+08:00",
    status,
    error:
      status === "failed"
        ? { stage: "clusters", message: "聚类阶段连接中断", at: "2026-11-17T09:00:00+08:00" }
        : null,
    stats: {
      sessions: 1,
      versionUnresolvedSessions: 0,
      badCases: 2,
      potential: 2,
      attributed: 2,
      reused: 0,
      clusters: 1,
      byCategory: { flow: 0, context: 0, model: 0, prompt: 2, error: 0 },
    },
    progress: {
      unit: completed ? 5 : 0,
      total: 5,
      percent: completed ? 100 : 0,
      stageLabel: completed
        ? "第 5/5 步 · 聚类完成"
        : "第 1/5 步 · 选择范围中…",
      doneRounds: 0,
      accepted: 0,
    },
    final: null,
    blockedStage: null,
    retryAttempts: 0,
    nextRetryAt: null,
    evalStatus: { verdict: null, bestScore: null, initScore: null },
    workspace: {
      repoUrl: "https://example.invalid/skills.git",
      pushRepoUrl: "https://example.invalid/fork/skills.git",
      subDir: "skills/synthetic-review",
      repoPath: null,
      baseRef: null,
      baseCommit: null,
      branchName: null,
      workspacePath: null,
      remote: "origin",
      pushStatus: "idle",
      pushedAt: null,
      pushError: null,
    },
    lastEventSeq: 0,
    steps: [],
  };
}

function rangeStep(cacheEnabled = true, attributionPackageId?: string) {
  return {
    key: "range",
    index: 0,
    title: "选择范围",
    status: "done",
    clickable: true,
    detail: null,
    payload: {
      condition: {
        targetType: "skill",
        targetName: "synthetic-review",
        targetVersion: "synthetic-1",
        targetRevision: "digest:abc",
        from: "2026-10-01",
        to: "2026-10-31",
        policy: {
          preset: "default",
          includeSelfReport: true,
          includeAfterObject: false,
          sameObjectOnly: true,
        },
        cacheEnabled,
        attributionPackageId,
        workspaceId,
      },
      stats: { sessions: 1, badCases: 2, potential: 2 },
    },
  };
}

function clustersStep() {
  return {
    key: "clusters",
    index: 4,
    title: "聚类与严重度",
    status: "done",
    clickable: true,
    detail: null,
    payload: {
      clusters: [
        {
          clusterId: "cluster-1",
          title: "长文档分块上下文丢失",
          description: "长文档分块时上下文被截断，模型缺少前文。",
          category: "prompt",
          caseCount: 1,
          confidence: 0.74,
          severity: 5.2,
          rank: 1,
          cases: [
            {
              badCaseId: "badcase-1234567890",
              title: "分块后缺少前文",
              objectName: "synthetic-review",
              badCaseType: "prompt",
              triggerAt: "2026-10-20T10:00:00+08:00",
              createdAt: "2026-10-20T10:05:00+08:00",
            },
          ],
        },
      ],
    },
  };
}

function attributionStep() {
  return {
    key: "attribution",
    index: 3,
    title: "对象归因",
    status: "done",
    clickable: true,
    detail: null,
    payload: {
      summary: { potential: 2, reused: 0, fresh: 2, nonTarget: 0 },
      rows: [
        {
          badCaseId: "badcase-1234567890",
          sessionId: "session-1",
          attributionId: "attr-1",
          category: "prompt",
          description: "长文档分块时上下文被截断。",
          source: "fresh",
          confidence: 0.8,
        },
      ],
    },
  };
}

async function mountPage() {
  const pinia = createPinia();
  setActivePinia(pinia);
  signInWithWorkspace({
    id: "user-1",
    username: "admin",
    displayName: "Administrator",
    role: "admin",
    mustChangePassword: false,
  });
  const router = createAppRouter();
  await router.push(runPath);
  await router.isReady();
  const wrapper = mount(ClusterPreview, {
    global: {
      plugins: [
        [
          VueQueryPlugin,
          {
            queryClient: new QueryClient({
              defaultOptions: { queries: { gcTime: 0, retry: false, staleTime: 0 } },
            }),
          },
        ],
        pinia,
        router,
      ],
    },
  });
  await flushPromises();
  await flushPromises();
  return { wrapper, router };
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("cluster preview page", () => {
  it("polls the run shell and does not request cluster steps before completion", async () => {
    const requests: string[] = [];
    server.use(
      http.get(detailPath, () => {
        requests.push("detail");
        return HttpResponse.json(runDetail("preparing"));
      }),
      http.get(rangePath, () => {
        requests.push("range");
        return HttpResponse.json(rangeStep());
      }),
      http.get(clustersPath, () => {
        requests.push("clusters");
        return HttpResponse.json(clustersStep());
      }),
    );

    const { wrapper } = await mountPage();

    expect(requests).toEqual(["detail"]);
    expect(wrapper.get("[data-testid='cluster-status']").text()).toContain("准备中");
    expect(wrapper.text()).toContain("正在关联 Session");
    expect(wrapper.findAll(".cluster")).toHaveLength(0);
    expect(
      wrapper.get("[data-testid='cluster-launch-full']").attributes("disabled"),
    ).toBeDefined();
    wrapper.unmount();
  });

  it("renders input summary, cluster cards, and source bad cases after completion", async () => {
    const requests: string[] = [];
    server.use(
      http.get(detailPath, () => {
        requests.push("detail");
        return HttpResponse.json(runDetail("completed"));
      }),
      http.get(rangePath, () => {
        requests.push("range");
        return HttpResponse.json(rangeStep());
      }),
      http.get(clustersPath, () => {
        requests.push("clusters");
        return HttpResponse.json(clustersStep());
      }),
      http.get(attributionPath, () => {
        requests.push("attribution");
        return HttpResponse.json(attributionStep());
      }),
      http.post(launchPath, () =>
        HttpResponse.json(
          { runId: "run-full", jobId: "job-full", status: "preparing" },
          { status: 202 },
        ),
      ),
    );

    const { wrapper } = await mountPage();

    expect(requests).toContain("detail");
    expect(requests).toContain("range");
    expect(requests).toContain("clusters");
    expect(requests).toContain("attribution");
    const status = wrapper.get("[data-testid='cluster-status']").text();
    expect(status).toContain("已完成");
    expect(status).toContain("第 5/5 步 · 聚类完成");
    expect(status).not.toContain("迭代");
    expect(wrapper.text()).toContain("问题聚类结果");
    expect(wrapper.text()).toContain("skill:synthetic-review@synthetic-1");
    expect(wrapper.text()).toContain("输入概况");
    expect(wrapper.text()).toContain("关联 Session");
    expect(wrapper.text()).toContain("潜在 bad case");
    expect(wrapper.text()).toContain("聚类数");
    expect(wrapper.text()).toContain("聚类出的 1 类问题");
    expect(wrapper.text()).toContain("以这批问题启动自进化");
    expect(wrapper.text()).toContain("2026-10-01 ~ 2026-10-31");
    expect(wrapper.text()).toContain("glm-5.3");
    expect(wrapper.text()).toContain("默认潜在策略");

    const clusters = wrapper.findAll(".cluster");
    expect(clusters).toHaveLength(1);
    expect(clusters[0]?.text()).toContain("长文档分块上下文丢失");
    expect(clusters[0]?.text()).toContain("bad case ×1");
    expect(clusters[0]?.text()).toContain("置信度 74%");
    expect(clusters[0]?.text()).toContain("严重程度 5.2");
    expect(wrapper.text()).toContain("聚类问题描述");
    expect(wrapper.text()).toContain("分块后缺少前文");
    const caseLink = wrapper.get(
      "a[href*='badcase-1234567890']",
    );
    expect(caseLink.attributes("href")).toBe(
      `/workspaces/${workspaceId}/sessions/session-1/errors?case=badcase-1234567890&tab=attr`,
    );
    wrapper.unmount();
  });

  it.each([
    { cacheEnabled: true, packageId: undefined },
    { cacheEnabled: false, packageId: "uploaded-skill-2" },
    { cacheEnabled: false, packageId: undefined },
  ])("launches a full run preserving cache=$cacheEnabled and package=$packageId", async ({ cacheEnabled, packageId }) => {
    const bodies: Record<string, unknown>[] = [];
    server.use(
      http.get(detailPath, () => HttpResponse.json(runDetail("completed"))),
      http.get(rangePath, () => HttpResponse.json(rangeStep(cacheEnabled, packageId))),
      http.get(clustersPath, () => HttpResponse.json(clustersStep())),
      http.get(attributionPath, () => HttpResponse.json(attributionStep())),
      http.get(
        `/api/workspaces/${workspaceId}/evolution/runs/run-full`,
        () => new HttpResponse(null, { status: 404 }),
      ),
      http.post(launchPath, async ({ request }) => {
        bodies.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json(
          { runId: "run-full", jobId: "job-full", status: "preparing" },
          { status: 202 },
        );
      }),
    );

    const { wrapper, router } = await mountPage();
    const navigated = new Promise<string>((resolve) => {
      router.afterEach((to) => resolve(to.path));
    });
    await wrapper.get("[data-testid='cluster-launch-full']").trigger("click");
    await flushPromises();
    await flushPromises();

    expect(bodies).toHaveLength(1);
    expect(bodies[0]).toMatchObject({
      targetType: "skill",
      targetName: "synthetic-review",
      targetVersion: "synthetic-1",
      from: "2026-10-01",
      to: "2026-10-31",
      mode: "full",
      cacheEnabled,
      policy: { preset: "default" },
    });
    if (packageId) expect(bodies[0]?.attributionPackageId).toBe(packageId);
    else expect(bodies[0]).not.toHaveProperty("attributionPackageId");
    expect(await navigated).toBe(`/workspaces/${workspaceId}/evolution/runs/run-full`);
    wrapper.unmount();
  });

  it("shows the run failure message without rendering cluster content", async () => {
    const requests: string[] = [];
    server.use(
      http.get(detailPath, () => {
        requests.push("detail");
        return HttpResponse.json(runDetail("failed"));
      }),
      http.get(rangePath, () => {
        requests.push("range");
        return HttpResponse.json(rangeStep());
      }),
      http.get(clustersPath, () => {
        requests.push("clusters");
        return HttpResponse.json(clustersStep());
      }),
    );

    const { wrapper } = await mountPage();

    expect(requests).toEqual(["detail"]);
    expect(wrapper.get("[data-testid='cluster-status']").text()).toContain("失败");
    expect(wrapper.text()).toContain("聚类未完成");
    expect(wrapper.text()).toContain("聚类阶段连接中断");
    expect(wrapper.findAll(".cluster")).toHaveLength(0);
    wrapper.unmount();
  });
});
