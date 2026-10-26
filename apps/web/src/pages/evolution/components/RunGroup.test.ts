// @vitest-environment jsdom

import type { EvolutionRunCard } from "@harness/contracts";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import RunCard from "./RunCard.vue";
import RunGroup from "./RunGroup.vue";

const card: EvolutionRunCard = {
  runId: "run-1",
  title: "run",
  mode: "full",
  target: { type: "skill", name: "deep-research", version: "v2.0.0" },
  window: { from: null, to: null },
  models: [],
  createdBy: null,
  createdAt: "2026-10-19T18:42:00+08:00",
  status: "running",
  error: null,
  stats: {
    sessions: 0,
    probes: 0,
    usedProbes: 0,
    clusters: 0,
    byAttributeType: { model: 0, prompt: 0, error: 0, nonIssue: 0 },
  },
  progress: {
    unit: 0,
    total: 5,
    percent: 0,
    stageLabel: "第 1/6 步 · 筛选输入中…",
    doneRounds: 0,
    accepted: 0,
  },
  final: null,
};

describe("RunGroup", () => {
  it("renders the active count, pulse, and cards", () => {
    const wrapper = mount(RunGroup, {
      props: {
        kind: "running",
        runs: [card],
      },
    });

    expect(wrapper.get(".group-label").text()).toContain("正在执行（1）");
    expect(wrapper.find(".pulse").exists()).toBe(true);
    expect(wrapper.findComponent(RunCard).props("run")).toEqual(card);
  });

  it("keeps the group count synchronized when the backend list refreshes", async () => {
    const wrapper = mount(RunGroup, {
      props: {
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

  it("renders the history count without an active pulse", () => {
    const wrapper = mount(RunGroup, {
      props: {
        kind: "history",
        runs: [{ ...card, status: "completed" }],
      },
    });

    expect(wrapper.get(".group-label").text()).toBe("历史记录（1）");
    expect(wrapper.find(".pulse").exists()).toBe(false);
  });

  it("uses distinct required copy for the two empty groups", () => {
    const running = mount(RunGroup, {
      props: { kind: "running", runs: [] },
    });
    const history = mount(RunGroup, {
      props: { kind: "history", runs: [] },
    });

    expect(running.text()).toContain("当前没有正在执行的自进化");
    expect(history.text()).toContain("暂无历史记录");
  });
});
