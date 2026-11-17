// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import type { TargetDetailResponse, TargetOverviewItem } from "@harness/contracts";

import { DEFAULT_OVERVIEW_STATE } from "../overviewUrl";
import TargetDetailCard from "./TargetDetailCard.vue";

const targets: TargetOverviewItem[] = [
  {
    targetId: "target-1",
    objectType: "skill",
    objectName: "synthetic-review",
    versions: ["synthetic-1", "main"],
    sessions: 1,
    potential: 3,
    attributed: 1,
    nonTarget: 1,
    unanalyzed: 1,
    evolvable: 2,
  },
  {
    targetId: "target-2",
    objectType: "agent",
    objectName: "review-agent",
    versions: ["main"],
    sessions: 0,
    potential: 0,
    attributed: 0,
    nonTarget: 0,
    unanalyzed: 0,
    evolvable: 0,
  },
];

const detail: TargetDetailResponse = {
  target: {
    targetId: "target-1",
    objectType: "skill",
    objectName: "synthetic-review",
    defaultRef: "main",
    versions: ["synthetic-1", "main"],
  },
  stats: { sessions: 1, potential: 3, distinctCases: 3, versions: 2 },
  byVersion: [
    {
      version: "synthetic-1",
      potential: 3,
      attributed: 1,
      nonTarget: 1,
      unanalyzed: 1,
    },
    { version: "main", potential: 0, attributed: 0, nonTarget: 0, unanalyzed: 0 },
  ],
  bySource: [{ source: "Explore", total: 3, distinctCases: 3 }],
};

function state(overrides = {}) {
  return {
    ...DEFAULT_OVERVIEW_STATE,
    tab: "targets" as const,
    detailTarget: "target-1",
    ...overrides,
  };
}

function mountCard(overrides = {}) {
  return mount(TargetDetailCard, {
    props: {
      targets,
      state: state(),
      sharedWindow: { from: "2026-10-01", to: "2026-11-16" },
      detail,
      ...overrides,
    },
  });
}

describe("TargetDetailCard", () => {
  it("renders stats, both distributions, and the version footnote", () => {
    const wrapper = mountCard();
    expect(wrapper.get("[data-testid='ov-target-detail-potential']").text()).toBe(
      "3",
    );
    expect(wrapper.findAll("[data-testid='ov-target-detail-version-row']")).toHaveLength(2);
    expect(wrapper.findAll("[data-testid='ov-target-detail-source-row']")).toHaveLength(1);
    expect(wrapper.text()).toContain("当前查看全部 2 个");
  });

  it("emits independent target, version, limit, and window changes", async () => {
    const wrapper = mountCard();

    await wrapper.get("[data-testid='ov-target-detail-target']").setValue("target-2");
    expect(wrapper.emitted("update:target")?.at(-1)).toEqual(["target-2"]);

    await wrapper.get("input[data-version='main']").setValue(true);
    expect(wrapper.emitted("update:versions")?.at(-1)).toEqual([["main"]]);

    await wrapper.get("[data-testid='ov-target-detail-limit-all']").trigger("click");
    expect(wrapper.emitted("update:limit")?.at(-1)).toEqual(["all"]);

    await wrapper.get("[data-testid='ov-target-detail-from']").setValue("2026-10-05");
    expect(wrapper.emitted("update:window")?.at(-1)).toEqual([
      { from: "2026-10-05", to: "2026-11-16" },
    ]);
  });

  it("shows the follow action only for an overridden window", async () => {
    const wrapper = mountCard({
      state: state({ detailFrom: "2026-10-01", detailTo: "2026-10-31" }),
    });
    await wrapper.get("[data-testid='ov-target-detail-follow']").trigger("click");
    expect(wrapper.emitted("update:window")?.at(-1)).toEqual([null]);

    const empty = mountCard({ targets: [], detail: null });
    expect(empty.find("[data-testid='ov-target-detail-empty']").exists()).toBe(true);
    await empty.get("[data-testid='ov-target-detail-empty-create']").trigger("click");
    expect(empty.emitted("create")).toHaveLength(1);
  });
});
