// @vitest-environment jsdom

import { flushPromises, mount } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { createPinia, setActivePinia } from "pinia";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { server } from "../../test/server";
import { queryKeys } from "../../api/queryKeys";
import { useAuthStore } from "../../stores/auth";
import { createAppRouter } from "../../router";
import TopNav from "./TopNav.vue";
import TopNavSource from "./TopNav.vue?raw";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("top navigation user area", () => {
  it("styles the rendered user popover button", () => {
    expect(TopNavSource).toContain(".user-popover button:hover");
    expect(TopNavSource).not.toContain(".user-area button:hover");
  });

  it("shows the current user and clears session state on logout", async () => {
    server.use(http.post("/api/auth/logout", () => new HttpResponse(null, { status: 204 })));
    const pinia = createPinia();
    setActivePinia(pinia);
    const store = useAuthStore();
    store.setSession({
      accessToken: "access",
      expiresIn: 1_800,
      user: {
        id: "u-1",
        username: "operator",
        displayName: "操作员",
        role: "member",
        mustChangePassword: false,
      },
    });
    const queryClient = new QueryClient();
    queryClient.setQueryData(["sessions"], [{ id: "s-1" }]);
    const router = createAppRouter();
    await router.push("/sessions");
    await router.isReady();
    const wrapper = mount(TopNav, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient }], pinia, router],
      },
    });

    expect(wrapper.text()).toContain("操作员");
    expect(wrapper.get("details.user-menu summary").text()).toBe("操作员");
    await wrapper.get("button[data-testid='logout']").trigger("click");
    await flushPromises();

    await vi.waitFor(() => {
      expect(store.user).toBeNull();
      expect(queryClient.getQueryData(["sessions"])).toBeUndefined();
      expect(router.currentRoute.value.path).toBe("/login");
    });
  });

  it("renders the prototype two-entry navigation and the optional demo badge", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    useAuthStore().setSession({
      accessToken: "access",
      expiresIn: 1_800,
      user: {
        id: "u-1",
        username: "operator",
        displayName: "操作员",
        role: "member",
        mustChangePassword: false,
      },
    });
    const router = createAppRouter();
    await router.push("/sessions");
    await router.isReady();

    const wrapper = mount(TopNav, {
      props: { demo: true },
      global: {
        plugins: [[VueQueryPlugin, { queryClient: new QueryClient() }], pinia, router],
      },
    });

    expect(wrapper.findAll("nav .tn-item")).toHaveLength(2);
    expect(wrapper.find("nav").text()).toContain("Session 错误查看");
    expect(wrapper.find("nav").text()).toContain("自进化");
    expect(wrapper.find("nav").text()).not.toContain("Errors");
    expect(wrapper.get("[data-testid='demo-badge']").text()).toContain("演示数据");
    expect(wrapper.get(".brand").text()).toContain("Harness Evolution");
  });

  it("keeps the prototype active state across session sub-routes", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    useAuthStore().setSession({
      accessToken: "access",
      expiresIn: 1_800,
      user: {
        id: "u-1",
        username: "operator",
        displayName: "操作员",
        role: "member",
        mustChangePassword: false,
      },
    });
    const router = createAppRouter();
    await router.push("/sessions/root-1/errors");
    await router.isReady();

    const wrapper = mount(TopNav, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient: new QueryClient() }], pinia, router],
      },
    });

    const items = wrapper.findAll("nav .tn-item");
    expect(items).toHaveLength(2);
    expect(wrapper.get("#tn-sessions").classes("active")).toBe(true);
    expect(wrapper.get("#tn-sessions").text()).toContain("Session 错误查看");
    expect(wrapper.get("#tn-evo").classes("active")).toBe(false);
    expect(wrapper.findAll("nav .tn-item.active")).toHaveLength(1);
    expect(wrapper.get(".tn-note").text()).toContain("点击 ID 跨页溯源");
  });

  it("keeps the compact brand and demo state accessible", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    useAuthStore().setSession({
      accessToken: "access",
      expiresIn: 1_800,
      user: {
        id: "u-1",
        username: "operator",
        displayName: "操作员",
        role: "member",
        mustChangePassword: false,
      },
    });
    const router = createAppRouter();
    await router.push("/sessions");
    await router.isReady();

    const wrapper = mount(TopNav, {
      props: { demo: true },
      global: {
        plugins: [[VueQueryPlugin, { queryClient: new QueryClient() }], pinia, router],
      },
    });

    expect(wrapper.get(".brand").attributes("aria-label")).toBe("Harness Evolution");
    expect(wrapper.get("[data-testid='demo-badge']").text()).toBe("演示数据");
  });

  it("shows pending acquisition detail without exposing it to members as an action", async () => {
    server.use(
      http.get("/api/acquisition/status", () =>
        HttpResponse.json({
          activeJobId: null,
          status: "idle",
          payloadTable: "trajectory_payloads",
          pending: 3,
          processed: 8,
          imported: 4,
          skipped: 1,
          lastRunAt: "2026-10-26T08:00:00+08:00",
          nextRunAt: "2026-10-26T08:01:00+08:00",
          errors: [
            {
              sessionId: "s-1",
              agentId: "a-1",
              lineNo: 3,
              code: "INVALID_JSONL_LINE",
              message: "raw diagnostic"
            }
          ],
          badCaseSync: {
            total: 12,
            synced: 7,
            unsynced: 5,
            syncing: 1,
            failed: 2,
            status: "idle",
            lastRunAt: "2026-10-26T08:00:00+08:00",
            lastError: null
          }
        }),
      ),
    );
    const pinia = createPinia();
    setActivePinia(pinia);
    useAuthStore().setSession({
      accessToken: "access",
      expiresIn: 1_800,
      user: {
        id: "u-1",
        username: "operator",
        displayName: "操作员",
        role: "member",
        mustChangePassword: false,
      },
    });
    const router = createAppRouter();
    await router.push("/sessions");
    await router.isReady();
    const wrapper = mount(TopNav, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient: new QueryClient() }], pinia, router],
      },
    });
    await flushPromises();

    expect(wrapper.get("[data-testid='sync-status']").text()).toContain("待处理 3");
    expect(wrapper.get("[data-testid='sync-status']").attributes("aria-label")).toContain(
      "已处理 8",
    );
    expect(
      wrapper.get("[data-testid='sync-status']").attributes("aria-label"),
    ).toContain("空闲");
    expect(
      wrapper.get("[data-testid='sync-status']").attributes("aria-label"),
    ).toContain("有一行轨迹无法解析");
    expect(
      wrapper.get("[data-testid='sync-status']").attributes("aria-label"),
    ).toContain("问题轨迹 总 12 已同步 7 未同步 5");
    expect(wrapper.get("[data-testid='sync-problem-badge']").text()).toContain(
      "问题轨迹 7/12",
    );
    expect(wrapper.get("[data-testid='sync-problem']").text()).toContain(
      "未同步 5",
    );
    expect(
      wrapper.get("[data-testid='sync-status']").attributes("aria-label"),
    ).not.toContain("raw diagnostic");
    expect(wrapper.find("[data-testid='sync-now']").exists()).toBe(false);
  });

  it("shows a failed bad-case sync state without exposing raw errors", async () => {
    server.use(
      http.get("/api/acquisition/status", () =>
        HttpResponse.json({
          activeJobId: null,
          status: "idle",
          payloadTable: "trajectory_payloads",
          pending: 0,
          processed: 0,
          imported: 0,
          skipped: 0,
          lastRunAt: null,
          nextRunAt: null,
          errors: [],
          badCaseSync: {
            total: 2,
            synced: 0,
            unsynced: 2,
            syncing: 0,
            failed: 2,
            status: "failed",
            lastRunAt: "2026-10-30T08:00:00+08:00",
            lastError: "SESSION_QUERY_TIMEOUT"
          }
        }),
      ),
    );
    const pinia = createPinia();
    setActivePinia(pinia);
    useAuthStore().setSession({
      accessToken: "access",
      expiresIn: 1_800,
      user: {
        id: "u-1",
        username: "operator",
        displayName: "操作员",
        role: "member",
        mustChangePassword: false,
      },
    });
    const router = createAppRouter();
    await router.push("/sessions");
    await router.isReady();
    const wrapper = mount(TopNav, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient: new QueryClient() }], pinia, router],
      },
    });
    await flushPromises();

    expect(wrapper.get("[data-testid='sync-problem']").text()).toContain(
      "轨迹查询超时",
    );
    expect(wrapper.get("[data-testid='sync-problem']").text()).toContain(
      "失败 2",
    );
  });

  it("lets admins process sync, poll the job, and invalidate session data", async () => {
    let calls = 0;
    server.use(
      http.get("/api/acquisition/status", () =>
        HttpResponse.json({
          activeJobId: null,
          status: "idle",
          payloadTable: "trajectory_payloads",
          pending: 1,
          processed: 0,
          imported: 0,
          skipped: 0,
          lastRunAt: null,
          nextRunAt: null,
          errors: [],
          badCaseSync: {
            total: 0,
            synced: 0,
            unsynced: 0,
            syncing: 0,
            failed: 0,
            status: "idle",
            lastRunAt: null,
            lastError: null
          }
        }),
      ),
      http.post("/api/acquisition/sync", () =>
        HttpResponse.json(
          { jobId: "job-1", status: "queued", reused: false },
          { status: 202 },
        ),
      ),
      http.get("/api/jobs/job-1", () => {
        calls += 1;
        return HttpResponse.json({
          jobId: "job-1",
          kind: "sync",
          refId: "sync-1",
          status: calls === 1 ? "running" : "completed",
          progress: calls === 1 ? 0.4 : 1,
          attempt: 1,
          createdBy: "u-admin",
          createdAt: "2026-10-26T08:00:00+08:00",
          startedAt: "2026-10-26T08:00:01+08:00",
          finishedAt: calls === 1 ? null : "2026-10-26T08:00:02+08:00",
          error: null
        });
      }),
    );
    const pinia = createPinia();
    setActivePinia(pinia);
    useAuthStore().setSession({
      accessToken: "access",
      expiresIn: 1_800,
      user: {
        id: "u-admin",
        username: "admin",
        displayName: "管理员",
        role: "admin",
        mustChangePassword: false,
      },
    });
    const queryClient = new QueryClient();
    queryClient.setQueryData(queryKeys.sessions, [{ id: "s-1" }]);
    const router = createAppRouter();
    await router.push("/sessions");
    await router.isReady();
    const wrapper = mount(TopNav, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient }], pinia, router],
      },
    });
    await flushPromises();

    await wrapper.get("[data-testid='sync-now']").trigger("click");
    await vi.waitFor(
      () => {
        expect(calls).toBe(2);
        expect(queryClient.getQueryState(queryKeys.sessions)?.isInvalidated).toBe(true);
      },
      { timeout: 2_000 },
    );
  });

  it.each([
    ["failed", "同步失败，请稍后重试"],
    ["interrupted", "同步已中断，请稍后重试"],
  ])(
    "shows a safe inline error when an admin-triggered sync is %s",
    async (jobStatus, expectedError) => {
    server.use(
      http.get("/api/acquisition/status", () =>
        HttpResponse.json({
          activeJobId: null,
          status: "idle",
          payloadTable: "trajectory_payloads",
          pending: 1,
          processed: 0,
          imported: 0,
          skipped: 0,
          lastRunAt: null,
          nextRunAt: null,
          errors: [],
          badCaseSync: {
            total: 0,
            synced: 0,
            unsynced: 0,
            syncing: 0,
            failed: 0,
            status: "idle",
            lastRunAt: null,
            lastError: null
          }
        }),
      ),
      http.post("/api/acquisition/sync", () =>
        HttpResponse.json(
          { jobId: `job-${jobStatus}`, status: "queued", reused: false },
          { status: 202 },
        ),
      ),
      http.get(`/api/jobs/job-${jobStatus}`, () =>
        HttpResponse.json({
          jobId: `job-${jobStatus}`,
          kind: "sync",
          refId: `sync-${jobStatus}`,
          status: jobStatus,
          progress: 0,
          attempt: 1,
          createdBy: "u-admin",
          createdAt: "2026-10-26T08:00:00+08:00",
          startedAt: "2026-10-26T08:00:01+08:00",
          finishedAt: "2026-10-26T08:00:02+08:00",
          error: "password=must-not-leak"
        }),
      ),
    );
    const pinia = createPinia();
    setActivePinia(pinia);
    useAuthStore().setSession({
      accessToken: "access",
      expiresIn: 1_800,
      user: {
        id: "u-admin",
        username: "admin",
        displayName: "管理员",
        role: "admin",
        mustChangePassword: false,
      },
    });
    const router = createAppRouter();
    await router.push("/sessions");
    await router.isReady();
    const wrapper = mount(TopNav, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient: new QueryClient() }], pinia, router],
      },
    });
    await flushPromises();

    await wrapper.get("[data-testid='sync-now']").trigger("click");
    await vi.waitFor(() => {
      expect(wrapper.get("[role='alert']").text()).toBe(expectedError);
    });
    expect(wrapper.text()).not.toContain("must-not-leak");
    },
  );

  it("keeps the shell stable when acquisition status is unavailable", async () => {
    server.use(
      http.get("/api/acquisition/status", () =>
        HttpResponse.json(
          { error: { code: "INTERNAL", message: "unavailable", details: {} } },
          { status: 503 },
        ),
      ),
    );
    const pinia = createPinia();
    setActivePinia(pinia);
    useAuthStore().setSession({
      accessToken: "access",
      expiresIn: 1_800,
      user: {
        id: "u-1",
        username: "operator",
        displayName: "操作员",
        role: "member",
        mustChangePassword: false,
      },
    });
    const router = createAppRouter();
    await router.push("/sessions");
    await router.isReady();
    const wrapper = mount(TopNav, {
      global: {
        plugins: [[VueQueryPlugin, { queryClient: new QueryClient() }], pinia, router],
      },
    });
    await flushPromises();

    expect(wrapper.find("[data-testid='sync-status']").exists()).toBe(false);
    expect(wrapper.find("nav").exists()).toBe(true);
    expect(wrapper.text()).toContain("操作员");
  });
});
