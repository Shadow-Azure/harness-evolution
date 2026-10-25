// @vitest-environment jsdom

import { flushPromises, mount } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { createPinia, setActivePinia } from "pinia";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import SessionsPage from "./Index.vue";
import { createAppRouter } from "../../router";
import { server } from "../../test/server";
import { useAuthStore } from "../../stores/auth";

const session = (overrides: Record<string, unknown> = {}) => ({
  id: "root-1",
  title: "分析 agent loop 与 LLM 层",
  short: "分析 agent loop",
  repo: "harness-evolution",
  startedAt: "2026-10-20T08:46:00+08:00",
  durationSeconds: 540,
  model: "claude-sonnet-4.5",
  status: "partial",
  skills: ["deep-research"],
  stats: {
    agents: 3,
    badCases: 2,
    badCasesPer100Messages: 1.5,
    errors: 4,
    failPer100Messages: 2,
    messages: 120,
    tokens: 1_250_000,
    tools: 18,
    userTurns: 6,
  },
  ...overrides,
});

function mockSessionApi(items = [session()]) {
  server.use(
    http.get("/api/sessions", () => HttpResponse.json({ items })),
    http.get("/api/sessions/:id", ({ params }) =>
      HttpResponse.json(
        items.find((item) => item.id === params.id) ?? {
          error: { code: "SESSION_NOT_FOUND", message: "missing" },
        },
      ),
    ),
  );
}

async function mountPage(path = "/sessions?q=agent&status=problem&sort=messages") {
  const pinia = createPinia();
  setActivePinia(pinia);
  const auth = useAuthStore();
  auth.setSession({
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
  const wrapper = mount(SessionsPage, {
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
  await flushPromises();
  return { router, wrapper };
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("session browser", () => {
  it("renders the independent detail response instead of stale list data", async () => {
    const listed = session({
      title: "List title",
      stats: { ...session().stats, errors: 1 },
    });
    const detailed = session({
      title: "Detail title",
      stats: { ...session().stats, errors: 9 },
    });
    server.use(
      http.get("/api/sessions", () => HttpResponse.json({ items: [listed] })),
      http.get("/api/sessions/:id", () => HttpResponse.json(detailed)),
    );

    const { wrapper } = await mountPage("/sessions/root-1");
    await flushPromises();

    const overview = wrapper.get("[data-testid='session-overview']");
    expect(overview.text()).toContain("Detail title");
    expect(overview.text()).not.toContain("List title");
    expect(overview.text()).toContain("9");
  });

  it("debounces search and persists the final status filter in the URL", async () => {
    const requestedQueries: string[] = [];
    server.use(
      http.get("/api/sessions", ({ request }) => {
        requestedQueries.push(new URL(request.url).searchParams.get("q") ?? "");
        return HttpResponse.json({ items: [session()] });
      }),
      http.get("/api/sessions/:id", () => HttpResponse.json(session())),
    );
    const { router, wrapper } = await mountPage("/sessions");
    await flushPromises();
    requestedQueries.length = 0;
    vi.useFakeTimers();

    try {
      const input = wrapper.get("[data-testid='search-input']");
      await input.setValue("a");
      await input.setValue("ab");
      await input.setValue("abc");
      expect(requestedQueries).toEqual([]);

      await vi.advanceTimersByTimeAsync(299);
      expect(router.currentRoute.value.query.q).toBeUndefined();
      await vi.advanceTimersByTimeAsync(1);
      await flushPromises();

      expect(router.currentRoute.value.query.q).toBe("abc");
      expect(requestedQueries).toEqual(["abc"]);
    } finally {
      vi.useRealTimers();
    }

    const completed = wrapper
      .findAll("button")
      .find((button) => button.text() === "完成");
    expect(completed).toBeDefined();
    await completed?.trigger("click");
    await flushPromises();
    expect(router.currentRoute.value.query.status).toBe("ok");
  });

  it("renders prototype cards and automatically selects the first session", async () => {
    mockSessionApi([
      session(),
      session({
        id: "root-2",
        title: "Obsidian 插件机制分析",
        short: "Obsidian 插件分析",
        status: "ok",
        repo: "obsidian-plugin",
      }),
    ]);
    const { router, wrapper } = await mountPage();
    await flushPromises();

    expect(wrapper.findAll("[data-testid='session-card']")).toHaveLength(2);
    expect(wrapper.get("[data-testid='session-browser-count']").text()).toContain("2");
    expect(wrapper.text()).toContain("用户轮次");
    expect(wrapper.text()).toContain("工具失败");
    expect(wrapper.findAll("[data-testid='density-bar']")).toHaveLength(4);
    expect(wrapper.get("[data-testid='session-overview']").text()).toContain(
      "分析 agent loop 与 LLM 层",
    );
    expect(wrapper.get("[data-testid='session-overview']").text()).toContain("1.25M");
    expect(wrapper.get("[data-testid='session-overview']").text()).toContain("有失败");
    expect(wrapper.find("[role='listbox']").exists()).toBe(true);
    const firstCard = wrapper.get("[data-testid='session-card']");
    expect(firstCard.attributes("role")).toBe("option");
    expect(firstCard.attributes("aria-selected")).toBe("true");
    expect(firstCard.text()).toContain("有失败");
    expect(router.currentRoute.value.path).toBe("/sessions/root-1");
    expect(router.currentRoute.value.query).toEqual({
      q: "agent",
      sort: "messages",
      status: "problem",
    });
    expect(wrapper.text()).not.toContain("暂无会话");
    expect(wrapper.find("[data-testid='tree-placeholder']").exists()).toBe(true);
  });

  it("restores URL state and keeps the active card tied to the route", async () => {
    mockSessionApi([
      session(),
      session({ id: "root-2", title: "Second" }),
    ]);
    const { router, wrapper } = await mountPage("/sessions/root-2?q=agent&status=all&sort=latest");
    await flushPromises();

    expect(router.currentRoute.value.path).toBe("/sessions/root-2");
    expect(wrapper.get(".session-browser").attributes("data-selected-id")).toBe("root-2");
    expect(wrapper.get("[data-testid='search-input']").element).toHaveProperty(
      "value",
      "agent",
    );
    const cards = wrapper.findAll("[data-testid='session-card']");
    expect(cards.map((card) => card.attributes("data-selected"))).toEqual([
      "false",
      "true",
    ]);
  });

  it("keeps empty filters and list failures actionable", async () => {
    mockSessionApi([]);
    const empty = await mountPage("/sessions?q=none");
    await flushPromises();

    expect(empty.wrapper.text()).toContain("没有匹配当前筛选的 session");
    expect(empty.wrapper.find("[data-testid='session-overview']").text()).toContain(
      "从左侧选择",
    );

    server.use(
      http.get("/api/sessions", () =>
        HttpResponse.json(
          { error: { code: "SESSIONS_UNAVAILABLE", message: "unavailable" } },
          { status: 500 },
        ),
      ),
    );
    const failed = await mountPage("/sessions");
    await flushPromises();

    expect(failed.wrapper.text()).toContain("Session 列表加载失败");
    expect(failed.wrapper.get("[role='alert'] button").text()).toContain("重试");
  });
});
