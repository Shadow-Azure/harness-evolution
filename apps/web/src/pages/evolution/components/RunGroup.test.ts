// @vitest-environment jsdom

import type { EvolutionRunCard } from "@harness/contracts";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import RunCard from "./RunCard.vue";
import RunGroup from "./RunGroup.vue";

const card: EvolutionRunCard = {
  runId: "run-1",
  controlState: "running", canPause: false, canResume: false,
  title: "run",
  mode: "full",
  target: { type: "skill", name: "deep-research", version: "v2.0.0" },
  window: { from: null, to: null },
  models: [],
  policy: { preset: "default" },
  cacheEnabled: false,
  createdBy: null,
  createdAt: "2026-10-19T18:42:00+08:00",
  status: "running",
  error: null,
  stats: {
    sessions: 0,
    versionUnresolvedSessions: 0,
    badCases: 0,
    potential: 0,
    attributed: 0,
    reused: 0,
    clusters: 0,
    byCategory: { model: 0, prompt: 0, error: 0 },
  },
  progress: {
    unit: 0,
    total: 7,
    percent: 0,
    stageLabel: "第 1/7 步 · 选择范围中…",
    doneRounds: 0,
    accepted: 0,
  },
  final: null,
};

describe("RunGroup", () => {
  it("renders the active count, pulse, and cards", () => {
    const wrapper = mount(RunGroup, {
      props: {
        wid: "ws-test",
        workspaceName: "测试空间",
        kind: "running",
        runs: [card],
      },
    });

    expect(wrapper.get(".group-label").text()).toContain("正在执行（1）");
    expect(wrapper.find(".pulse").exists()).toBe(true);
    expect(wrapper.findComponent(RunCard).props("run")).toEqual(card);
    expect(wrapper.findComponent(RunCard).props("workspaceName")).toBe(
      "测试空间",
    );
  });

  it("keeps the group count synchronized when the backend list refreshes", async () => {
    const wrapper = mount(RunGroup, {
      props: {
        wid: "ws-test",
        workspaceName: "测试空间",
        kind: "running",
        runs: [card],
      },
    });

    await wrapper.setProps({
      runs: [card, { ...card, runId: "run-2", title: "run 2" }],
    });

    expect(wrapper.get(".group-label").text()).toContain("正在执行（2）");
    expect(wrapper.findAll(".run-card")).toHaveLength(2);
  });

  it("forwards a card open intent to the page", async () => {
    const wrapper = mount(RunGroup, {
      props: {
        wid: "ws-test",
        workspaceName: "测试空间",
        kind: "running",
        runs: [card],
      },
    });

    await wrapper.get(".run-card-link").trigger("click");
    expect(wrapper.emitted("open")).toEqual([
      ["/workspaces/ws-test/evolution/runs/run-1"],
    ]);
  });

  it("renders the history count without an active pulse", () => {
    const wrapper = mount(RunGroup, {
      props: {
        wid: "ws-test",
        workspaceName: "测试空间",
        kind: "history",
        runs: [{ ...card, status: "completed" }],
      },
    });

    expect(wrapper.get(".group-label").text()).toBe("历史记录（1）");
    expect(wrapper.find(".pulse").exists()).toBe(false);
  });

  it("uses distinct required copy for the two empty groups", () => {
    const running = mount(RunGroup, {
      props: { wid: "ws-test", workspaceName: "测试空间", kind: "running", runs: [] },
    });
    const history = mount(RunGroup, {
      props: { wid: "ws-test", workspaceName: "测试空间", kind: "history", runs: [] },
    });

    expect(running.text()).toContain("当前没有正在执行的自进化");
    expect(history.text()).toContain("暂无历史记录");
  });
});
