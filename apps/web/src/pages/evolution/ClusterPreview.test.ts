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

function runDetail(status: string) {
  return {
    runId,
    title: "cluster only run",
    mode: "cluster_only",
    target: { type: "skill", name: "synthetic-review", version: "synthetic-1" },
    window: { from: "2026-10-01", to: "2026-10-31" },
    models: ["glm-5.3"],
    createdBy: "Administrator",
    createdAt: "2026-11-17T08:00:00+08:00",
    status,
    error: null,
    stats: {
      sessions: 1,
      versionUnresolvedSessions: 0,
      badCases: 2,
      potential: 2,
      attributed: 2,
      reused: 0,
      clusters: 1,
      byCategory: { model: 0, prompt: 2, error: 0 },
    },
    progress: {
      unit: 5,
      total: 7,
      percent: 71,
      stageLabel: "第 5/7 步 · 聚类与严重度排序中…",
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
  return wrapper;
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("cluster preview page", () => {
  it("reads the live run snapshot instead of the stale run list", async () => {
    const requests: string[] = [];
    server.use(
      http.get(detailPath, () => {
        requests.push("detail");
        return HttpResponse.json(runDetail("completed"));
      }),
    );

    const wrapper = await mountPage();

    expect(requests).toEqual(["detail"]);
    expect(wrapper.get("[data-testid='cluster-status']").text()).toContain(
      "completed",
    );
    expect(wrapper.get("[data-testid='cluster-status']").text()).toContain(
      "第 5/7 步",
    );
    expect(wrapper.text()).toContain("仅聚类分析");
    wrapper.unmount();
  });
});
