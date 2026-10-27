// @vitest-environment jsdom

import type { EvolutionRunEvent } from "@harness/contracts";
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { http, HttpResponse } from "msw";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { server } from "../../../test/server";
import RunLogPanel from "./RunLogPanel.vue";

const wrappers: VueWrapper[] = [];

const steps = [
  ["input", "筛选输入"],
  ["clusters", "问题聚类"],
  ["attribution", "LLM 归因置信度"],
  ["severity", "严重程度排序"],
  ["iteration", "迭代优化"],
  ["final", "测试集终评"],
] as const;

const availableSteps = steps.map(([key, title], index) => ({
  index,
  key,
  title,
  status:
    index === 4
      ? ("active" as const)
      : index < 4
        ? ("done" as const)
        : ("pending" as const),
  clickable: index < 5,
  detail: null,
}));

function event(
  seq: number,
  overrides: Partial<EvolutionRunEvent> = {},
): EvolutionRunEvent {
  return {
    seq,
    eventType: "candidate_committed",
    level: "info",
    stage: "candidate",
    stepIndex: 4,
    clusterId: "cluster-abc123456",
    roundId: "round-1",
    jobId: "job-1",
    message: `event ${seq}`,
    createdAt: `2026-10-28T08:00:0${seq}+08:00`,
    payload: { durationMs: 812 },
    error: null,
    ...overrides,
  };
}

function page(
  items: EvolutionRunEvent[],
  nextSeq = items.at(-1)?.seq ?? 0,
  hasMore = false,
) {
  return { items, nextSeq, hasMore };
}

async function mountPanel() {
  const wrapper = mount(RunLogPanel, {
    props: {
      runId: "run-events",
      steps: availableSteps,
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

describe("RunLogPanel", () => {
  it("renders REST events and jumps to valid step and cluster targets", async () => {
    server.use(
      http.get("/api/evolution/runs/run-events/events", () =>
        HttpResponse.json(page([event(1), event(2)]))),
    );
    const wrapper = await mountPanel();

    expect(wrapper.findAll("[data-event-seq]")).toHaveLength(2);
    expect(wrapper.text()).toContain("candidate_committed");
    expect(wrapper.text()).toContain("812ms");

    await wrapper.get(".jump:not(.cluster)").trigger("click");
    await wrapper.get(".jump.cluster").trigger("click");

    expect(wrapper.emitted("select-step")).toEqual([["iteration"]]);
    expect(wrapper.emitted("focus-cluster")).toEqual([
      ["cluster-abc123456"],
    ]);
  });

  it("filters by level and appends a non-duplicated next page", async () => {
    const queries: URLSearchParams[] = [];
    server.use(
      http.get("/api/evolution/runs/run-events/events", ({ request }) => {
        const query = new URL(request.url).searchParams;
        queries.push(query);
        if (query.get("level") === "error") {
          return HttpResponse.json(page([event(2, { level: "error" })]));
        }
        if (query.get("afterSeq") === "0") {
          return HttpResponse.json(page([event(1)], 1, true));
        }
        return HttpResponse.json(page([event(1), event(2, { level: "error" })]));
      }),
    );
    const wrapper = await mountPanel();

    await wrapper.get("[data-testid='load-more-events']").trigger("click");
    await flushPromises();
    expect(wrapper.findAll("[data-event-seq]")).toHaveLength(2);
    expect(wrapper.text()).toContain("已加载全部记录");
    expect(wrapper.text()).not.toContain("已到最早记录");

    const errorFilter = wrapper
      .findAll(".filters button")
      .find((button) => button.text() === "错误");
    expect(errorFilter).toBeDefined();
    await errorFilter!.trigger("click");
    await flushPromises();

    expect(queries.at(-1)?.get("level")).toBe("error");
    expect(wrapper.text()).toContain("event 2");
  });

  it("keeps redacted error details collapsed until requested and copies them", async () => {
    const writes: string[] = [];
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: async (value: string) => writes.push(value) },
    });
    server.use(
      http.get("/api/evolution/runs/run-events/events", () =>
        HttpResponse.json(
          page([
            event(3, {
              level: "error",
              eventType: "run_failed",
              message: "任务失败",
              error: {
                type: "GitError",
                message: "remote rejected",
                detail: "token=<redacted>\nend",
              },
            }),
          ]),
        )),
    );
    const wrapper = await mountPanel();

    const details = wrapper.get("details");
    expect(details.attributes("open")).toBeUndefined();
    await wrapper.get("summary").trigger("click");
    await wrapper.get(".copy-detail").trigger("click");
    await flushPromises();

    expect(writes).toEqual(["GitError\nremote rejected\ntoken=<redacted>\nend"]);
    expect(wrapper.text()).toContain("已复制");
  });

  it("does not link to a future or missing navigation target", async () => {
    server.use(
      http.get("/api/evolution/runs/run-events/events", () =>
        HttpResponse.json(
          page([
            event(1, {
              stepIndex: 5,
              clusterId: null,
            }),
            event(2, {
              stepIndex: null,
              clusterId: null,
            }),
          ]),
        )),
    );
    const wrapper = await mountPanel();

    expect(wrapper.find(".jump").exists()).toBe(false);
  });

  it("pauses auto-scroll when the operator scrolls upward", async () => {
    server.use(
      http.get("/api/evolution/runs/run-events/events", () =>
        HttpResponse.json(page([event(1), event(2)]))),
    );
    const wrapper = await mountPanel();
    const scroller = wrapper.get("[data-testid='event-scroll']");
    Object.defineProperties(scroller.element, {
      scrollHeight: { configurable: true, value: 1000 },
      clientHeight: { configurable: true, value: 300 },
      scrollTop: { configurable: true, value: 100, writable: true },
    });

    await scroller.trigger("scroll");

    expect(wrapper.text()).toContain("自动滚动已暂停");
  });

  it("shows explicit empty and retryable error states", async () => {
    let attempts = 0;
    server.use(
      http.get("/api/evolution/runs/run-events/events", () => {
        attempts += 1;
        return attempts === 1
          ? HttpResponse.json(
              { error: { code: "INTERNAL", message: "failed" } },
              { status: 500 },
            )
          : HttpResponse.json(page([]));
      }),
    );
    const wrapper = await mountPanel();

    expect(wrapper.text()).toContain("执行日志读取失败，请重试");
    await wrapper.get(".error-state button").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("还没有执行日志");
    expect(wrapper.text()).toContain("事件会持久出现在这里");
  });
});
