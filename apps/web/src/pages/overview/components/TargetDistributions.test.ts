// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import type { TargetOverviewItem, TargetTrendBucket } from "@harness/contracts";

import TargetDistributions from "./TargetDistributions.vue";

const items: TargetOverviewItem[] = [
  {
    targetId: "target-1",
    objectType: "skill",
    objectName: "synthetic-review",
    versions: ["main"],
    sessions: 3,
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
    sessions: 1,
    potential: 1,
    attributed: 1,
    nonTarget: 0,
    unanalyzed: 0,
    evolvable: 1,
  },
];

const buckets: TargetTrendBucket[] = [
  {
    bucket: "2026-10-19",
    label: "10-19",
    attributed: 1,
    nonTarget: 1,
    unanalyzed: 1,
    byTarget: [
      {
        targetId: "target-1",
        objectType: "skill",
        objectName: "synthetic-review",
        attributed: 1,
        nonTarget: 1,
        unanalyzed: 1,
      },
      {
        targetId: "target-2",
        objectType: "agent",
        objectName: "review-agent",
        attributed: 1,
        nonTarget: 0,
        unanalyzed: 0,
      },
    ],
  },
];

describe("TargetDistributions", () => {
  it("derives both distributions from the target list and trend buckets", () => {
    const wrapper = mount(TargetDistributions, {
      props: { items, buckets, selectedTargets: [], selectedStates: [] },
    });
    expect(wrapper.findAll("[data-testid='ov-target-assoc-row']")).toHaveLength(2);
    expect(wrapper.findAll("[data-testid='ov-target-potential-row']")).toHaveLength(2);
    expect(wrapper.text()).toContain("3 关联 · 3 潜在");
    expect(wrapper.text()).toContain("3 · 是 1 / 非 1 / 未 1");
  });

  it("filters targets and states and explains an empty space", () => {
    const wrapper = mount(TargetDistributions, {
      props: {
        items,
        buckets,
        selectedTargets: ["target-2"],
        selectedStates: ["attributed"],
      },
    });
    expect(wrapper.findAll("[data-testid='ov-target-potential-row']")).toHaveLength(1);
    expect(wrapper.text()).toContain("1 · 是 1 / 非 0 / 未 0");

    const empty = mount(TargetDistributions, {
      props: { items: [], buckets: [], selectedTargets: [], selectedStates: [] },
    });
    expect(empty.text()).toContain("当前空间还没有进化对象");
  });
});
