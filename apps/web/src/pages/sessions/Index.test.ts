// @vitest-environment jsdom

import { flushPromises, mount } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { createPinia, setActivePinia } from "pinia";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import SessionsPage from "./Index.vue";
import { demoCoreTree } from "../../components/agent-tree/fixtures/demo-nested";
import { createAppRouter } from "../../router";
import { server } from "../../test/server";
import { useAuthStore } from "../../stores/auth";

vi.mock("../../components/agent-tree/AgentTree.vue", async () => {
  const { defineComponent, h } = await import("vue");
  const AgentTree = defineComponent({
    name: "AgentTree",
    props: {
      tree: { type: Object, required: true },
      expanded: { type: Array, default: () => [] },
      activeAgentId: { type: String, default: null },
      activeEventIndex: { type: Number, default: null },
    },
    emits: ["node-select", "toggle-expanded"],
    setup(props, { emit }) {
      return () => {
        const tree = props.tree as { agents: unknown[] };
        return h("div", { "data-testid": "agent-tree" }, [
          h("span", `agents:${tree.agents.length}`),
          h(
            "button",
            {
              type: "button",
              onClick: () => emit("node-select", "main"),
            },
            `selected:${props.activeAgentId}:evidence:${props.activeEventIndex}:expanded:${props.expanded.join(",")}`,
          ),
        ]);
      };
    },
  });
  return {
    __esModule: true,
    __isKeepAlive: false,
    __isTeleport: false,
    default: AgentTree,
  };
});

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
  const tree = {
    ...demoCoreTree,
    sessionId: items[0]?.id ?? "root-1",
  };
  server.use(
    http.get("/api/sessions", () => HttpResponse.json({ items })),
    http.get("/api/sessions/:id", ({ params }) =>
      HttpResponse.json(
        items.find((item) => item.id === params.id) ?? {
          error: { code: "SESSION_NOT_FOUND", message: "missing" },
        },
      ),
    ),
    http.get("/api/sessions/:id/tree", () =>
      HttpResponse.json(tree),
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
      http.get("/api/sessions/:id/tree", () =>
        HttpResponse.json({ ...demoCoreTree, sessionId: "root-1" }),
      ),
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
      http.get("/api/sessions/:id/tree", () =>
        HttpResponse.json({ ...demoCoreTree, sessionId: "root-1" }),
      ),
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

  it("cancels a pending debounced search when navigation changes the query", async () => {
    mockSessionApi([session()]);
    const { router, wrapper } = await mountPage("/sessions");
    await flushPromises();
    vi.useFakeTimers();

    try {
      await wrapper.get("[data-testid='search-input']").setValue("stale");
      await router.push({
        path: "/sessions/root-1",
        query: { q: "server" },
      });
      await flushPromises();
      await vi.advanceTimersByTimeAsync(300);
      await flushPromises();

      expect(router.currentRoute.value.query.q).toBe("server");
    } finally {
      vi.useRealTimers();
    }
  });

  it("renders prototype cards and automatically selects the first session", async () => {
    mockSessionApi([
      session({ short: "", title: "Fallback title" }),
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
      "Fallback title",
    );
    expect(wrapper.get("[data-testid='session-overview']").text()).toContain("1.3M");
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
    expect(wrapper.find("[data-testid='agent-tree-container']").exists()).toBe(true);
    expect(firstCard.text()).toContain("Fallback title");
  });

  it("loads the production tree independently and retries tree failures", async () => {
    const item = session();
    server.use(
      http.get("/api/sessions", () => HttpResponse.json({ items: [item] })),
      http.get("/api/sessions/:id", () => HttpResponse.json(item)),
      http.get("/api/sessions/:id/tree", () =>
        HttpResponse.json(
          { error: { code: "SESSION_NOT_FOUND", message: "missing" } },
          { status: 404 },
        ),
      ),
    );

    const { wrapper } = await mountPage("/sessions/root-1");
    await flushPromises();

    const overview = wrapper.get("[data-testid='session-overview']");
    expect(overview.text()).toContain("执行流读取失败");
    expect(overview.text()).toContain("重试");
    expect(overview.text()).toContain(item.title);
    expect(overview.find("[data-testid='tree-placeholder']").exists()).toBe(false);
  });

  it("supports listbox arrow, Home, and End keyboard navigation", async () => {
    mockSessionApi([
      session(),
      session({ id: "root-2", title: "Second" }),
      session({ id: "root-3", title: "Third" }),
    ]);
    const { router, wrapper } = await mountPage("/sessions/root-1");
    await flushPromises();

    const listbox = wrapper.get("[role='listbox']");
    const cards = wrapper.findAll("[data-testid='session-card']");

    await cards[0]?.trigger("keydown", { key: "ArrowDown" });
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/sessions/root-2");
    expect(wrapper.findAll("[data-testid='session-card']").map((card) =>
      card.attributes("tabindex"),
    )).toEqual(["-1", "0", "-1"]);

    await listbox.trigger("keydown", { key: "End" });
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/sessions/root-3");

    await listbox.trigger("keydown", { key: "Home" });
    await flushPromises();
    expect(router.currentRoute.value.path).toBe("/sessions/root-1");
  });

  it.each([
    ["partial", "problem"],
    ["fail", "fail"],
  ] as const)(
    "normalizes %s URLs to the failed chip and keeps its severity color",
    async (status, badgeClass) => {
      mockSessionApi([session({ status })]);
      const { wrapper } = await mountPage(`/sessions/root-1?status=${status}`);
      await flushPromises();

      const overview = wrapper.get("[data-testid='session-overview']");
      expect(overview.find(`.status-badge.${badgeClass}`).exists()).toBe(true);
      expect(overview.find(".status-badge.ok").exists()).toBe(false);
      expect(
        wrapper
          .findAll("button")
          .find((button) => button.text() === "有失败")
          ?.classes(),
      ).toContain("active");
    },
  );

  it("formats long durations, compact tokens, and density units like the prototype", async () => {
    mockSessionApi([
      session({
        durationSeconds: 63_420,
        stats: {
          ...session().stats,
          badCasesPer100Messages: 2.04,
          failPer100Messages: 2.04,
          tokens: 1_345_678,
        },
      }),
    ]);
    const { wrapper } = await mountPage("/sessions/root-1");
    await flushPromises();

    const overview = wrapper.get("[data-testid='session-overview']");
    expect(overview.text()).toContain("17h37m");
    expect(overview.text()).toContain("1.3M");
    expect(wrapper.findAll("[data-testid='density-bar']")[0]?.text()).toContain(
      "2.0/百消息",
    );
  });

  it("restores Agent and evidence state from a Session deep link", async () => {
    mockSessionApi([session()]);
    const { router, wrapper } = await mountPage(
      "/sessions/root-1?agent=agent-a&evidence=1",
    );
    await flushPromises();

    expect(router.currentRoute.value.query).toMatchObject({
      agent: "agent-a",
      evidence: "1",
    });
    expect(wrapper.get("[data-testid='agent-tree']").text()).toContain(
      "selected:agent-a:evidence:1",
    );
  });

  it("canonicalizes accepted deep-link query values", async () => {
    mockSessionApi([session()]);
    const { router } = await mountPage(
      "/sessions/root-1?agent=agent-a&evidence=01&case=case-1&tab=attr",
    );
    await flushPromises();

    expect(router.currentRoute.value.query).toEqual({
      agent: "agent-a",
      evidence: "1",
    });
  });

  it("expands collapsed ancestors before restoring a deep-linked Agent", async () => {
    const children = Array.from({ length: 9 }, (_, index) => ({
      agentId: `child-${index + 1}`,
      kind: "subagent" as const,
      label: `Child ${index + 1}`,
      desc: "",
      parentAgentId: "main",
      taskKind: null,
      agentType: "general-purpose",
      skillName: null,
      teamName: null,
      lines: 2,
      messagesCount: 1,
      tokensTotal: 0,
      toolsCount: 0,
      errorsCount: 0,
      events: [],
    }));
    const foldedTree = {
      sessionId: "root-1",
      overview: session(),
      agents: [
        {
          ...demoCoreTree.agents[0],
          events: children.map((child, index) => ({
            kind: "agent" as const,
            line: index + 1,
            messageOffset: index,
            name: child.label,
            desc: child.label,
            toolUseId: `tool-${index + 1}`,
          })),
        },
        ...children.map((child, index) => ({
          ...child,
          toolUseId: `tool-${index + 1}`,
        })),
      ],
      badCases: [],
    };
    server.use(
      http.get("/api/sessions", () =>
        HttpResponse.json({ items: [session()] }),
      ),
      http.get("/api/sessions/:id", () => HttpResponse.json(session())),
      http.get("/api/sessions/:id/tree", () =>
        HttpResponse.json(foldedTree),
      ),
    );

    const { wrapper } = await mountPage(
      "/sessions/root-1?agent=child-9",
    );
    await flushPromises();

    const tree = wrapper.get("[data-testid='agent-tree']").text();
    expect(tree).toContain("expanded:main");
    expect(tree).toContain("selected:child-9");
  });

  it("keeps an explicit Session isolated when filters exclude it", async () => {
    const other = session({ id: "root-2", title: "Other" });
    server.use(
      http.get("/api/sessions", () =>
        HttpResponse.json({ items: [other] }),
      ),
      http.get("/api/sessions/:id", () => HttpResponse.json(session())),
      http.get("/api/sessions/:id/tree", () =>
        HttpResponse.json(demoCoreTree),
      ),
    );

    const { router, wrapper } = await mountPage(
      "/sessions/root-1?q=filtered&agent=agent-a&evidence=1",
    );
    await flushPromises();

    expect(router.currentRoute.value.path).toBe("/sessions/root-1");
    expect(router.currentRoute.value.query.agent).toBe("agent-a");
    expect(wrapper.get("[data-testid='agent-tree']").text()).toContain(
      "selected:agent-a:evidence:1",
    );
    expect(wrapper.get(".session-browser").attributes("data-selected-id")).toBe(
      "root-1",
    );
  });

  it("writes Agent selection to the URL and clears stale evidence", async () => {
    mockSessionApi([session()]);
    const { router, wrapper } = await mountPage(
      "/sessions/root-1?agent=agent-a&evidence=1",
    );
    await flushPromises();

    await wrapper.get("[data-testid='agent-tree'] button").trigger("click");
    await flushPromises();

    expect(router.currentRoute.value.fullPath).toBe(
      "/sessions/root-1?agent=main",
    );
  });

  it("clears an Agent that no longer exists without changing Session", async () => {
    mockSessionApi([session()]);
    const { router, wrapper } = await mountPage(
      "/sessions/root-1?agent=missing&evidence=1",
    );
    await flushPromises();

    expect(router.currentRoute.value.fullPath).toBe("/sessions/root-1");
    expect(wrapper.get("[data-testid='deep-link-notice']").text()).toContain(
      "Agent 已不存在",
    );
    expect(wrapper.get("[data-testid='agent-tree']").text()).toContain(
      "selected:main:evidence:null",
    );
  });

  it("clears out-of-range evidence while retaining the Agent", async () => {
    mockSessionApi([session()]);
    const { router, wrapper } = await mountPage(
      "/sessions/root-1?agent=agent-a&evidence=99",
    );
    await flushPromises();

    expect(router.currentRoute.value.fullPath).toBe(
      "/sessions/root-1?agent=agent-a",
    );
    expect(wrapper.get("[data-testid='deep-link-notice']").text()).toContain(
      "证据位置",
    );
    expect(wrapper.get("[data-testid='agent-tree']").text()).toContain(
      "selected:agent-a:evidence:null",
    );
  });

  it("clears a stale deep-link notice when a later URL is valid", async () => {
    mockSessionApi([session()]);
    const { router, wrapper } = await mountPage(
      "/sessions/root-1?agent=missing&evidence=1",
    );
    await flushPromises();

    expect(wrapper.get("[data-testid='deep-link-notice']").text()).toContain(
      "Agent 已不存在",
    );

    await router.push("/sessions/root-1?agent=agent-a&evidence=1");
    await flushPromises();

    expect(wrapper.find("[data-testid='deep-link-notice']").exists()).toBe(false);
    expect(wrapper.get("[data-testid='agent-tree']").text()).toContain(
      "selected:agent-a:evidence:1",
    );
  });

  it("does not auto-select or request a tree for an invalid Session path", async () => {
    const detailRequests: string[] = [];
    const treeRequests: string[] = [];
    server.use(
      http.get("/api/sessions", () => HttpResponse.json({ items: [session()] })),
      http.get("/api/sessions/:id", ({ params }) => {
        detailRequests.push(String(params.id));
        return HttpResponse.json(session());
      }),
      http.get("/api/sessions/:id/tree", ({ params }) => {
        treeRequests.push(String(params.id));
        return HttpResponse.json(demoCoreTree);
      }),
    );
    const invalidId = "x".repeat(37);
    const { router, wrapper } = await mountPage(`/sessions/${invalidId}`);
    await flushPromises();

    expect(router.currentRoute.value.path).toBe(`/sessions/${invalidId}`);
    expect(detailRequests).toEqual([]);
    expect(treeRequests).toEqual([]);
    expect(wrapper.get("[data-testid='deep-link-notice']").text()).toContain(
      "Session 深链无效",
    );
    expect(wrapper.text()).not.toContain("从左侧选择一个 Session");
  });

  it("does not decode an encoded Session path a second time", async () => {
    const detailRequests: string[] = [];
    const treeRequests: string[] = [];
    server.use(
      http.get("/api/sessions", () => HttpResponse.json({ items: [session()] })),
      http.get("/api/sessions/:id", ({ params }) => {
        detailRequests.push(String(params.id));
        return HttpResponse.json(session());
      }),
      http.get("/api/sessions/:id/tree", ({ params }) => {
        treeRequests.push(String(params.id));
        return HttpResponse.json(demoCoreTree);
      }),
    );

    const { wrapper } = await mountPage("/sessions/a%2541b");
    await flushPromises();

    expect(detailRequests).toEqual([]);
    expect(treeRequests).toEqual([]);
    expect(wrapper.get("[data-testid='deep-link-notice']").text()).toContain(
      "Session 深链无效",
    );
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
    expect(empty.wrapper.find("[role='listbox']").exists()).toBe(false);
    expect(empty.wrapper.get(".empty-list").attributes("role")).toBe("status");

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
    expect(failed.wrapper.find("[role='listbox']").exists()).toBe(false);
  });
});
