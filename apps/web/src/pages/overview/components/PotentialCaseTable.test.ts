// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import PotentialCaseTable from "./PotentialCaseTable.vue";

const item = {
  badCaseId: "badcase-1",
  objectType: "skill" as const,
  objectName: "synthetic-review",
  objectVersion: "synthetic-1",
  source: "Explore",
  state: "attributed" as const,
  badCaseType: "self" as const,
  title: "检查结论缺少目标文件",
  createdAt: "2026-10-20T09:03:00+08:00",
  sessionId: "session-1",
  attributionId: "probe-1",
  category: "prompt" as const,
};

const filters = {
  caseTarget: "",
  caseSource: "",
  caseState: "all" as const,
  caseFrom: "",
  caseTo: "",
};

describe("PotentialCaseTable", () => {
  it("builds description and attribution deep links", () => {
    const wrapper = mount(PotentialCaseTable, {
      props: { wid: "ws-1", items: [item], total: 1, filters },
    });
    const links = wrapper.findAll("a.idlink");
    expect(links[0]?.attributes("href")).toBe(
      "/workspaces/ws-1/sessions/session-1/errors?case=badcase-1&tab=desc",
    );
    expect(links[1]?.attributes("href")).toBe(
      "/workspaces/ws-1/sessions/session-1/errors?case=badcase-1&tab=attr&at=probe-1",
    );
    expect(wrapper.text()).toContain("已分析 · 是该对象问题");
    expect(wrapper.text()).toContain("prompt");
  });

  it("emits every filter change and resets to the open filters", async () => {
    const wrapper = mount(PotentialCaseTable, {
      props: {
        wid: "ws-1",
        items: [item],
        total: 1,
        filters,
        targetOptions: [
          {
            targetId: "target-1",
            objectType: "skill",
            objectName: "synthetic-review",
            versions: ["main"],
            sessions: 0,
            potential: 0,
            attributed: 0,
            nonTarget: 0,
            unanalyzed: 0,
            evolvable: 0,
          },
        ],
        sourceOptions: ["Explore"],
      },
    });

    await wrapper.get("[data-testid='ov-target-case-target']").setValue("target-1");
    expect(wrapper.emitted("update:filters")?.at(-1)).toEqual([
      { caseTarget: "target-1" },
    ]);

    await wrapper.get("[data-testid='ov-target-case-source']").setValue("Explore");
    expect(wrapper.emitted("update:filters")?.at(-1)).toEqual([
      { caseSource: "Explore" },
    ]);

    await wrapper.get("[data-testid='ov-target-case-state']").setValue("nonTarget");
    expect(wrapper.emitted("update:filters")?.at(-1)).toEqual([
      { caseState: "nonTarget" },
    ]);

    await wrapper
      .get("[data-testid='ov-target-case-from']")
      .setValue("2026-10-01");
    await wrapper.setProps({
      filters: { ...filters, caseFrom: "2026-10-01" },
    });
    await wrapper.get("[data-testid='ov-target-case-to']").setValue("2026-10-31");
    expect(wrapper.emitted("update:filters")?.at(-1)).toEqual([
      { caseFrom: "2026-10-01", caseTo: "2026-10-31" },
    ]);

    await wrapper.get("[data-testid='ov-target-case-reset']").trigger("click");
    expect(wrapper.emitted("update:filters")?.at(-1)).toEqual([
      {
        caseTarget: "",
        caseSource: "",
        caseState: "all",
        caseFrom: "",
        caseTo: "",
      },
    ]);
  });

  it("pages a non-empty result and explains an empty workspace", async () => {
    const wrapper = mount(PotentialCaseTable, {
      props: { wid: "ws-1", items: [item], total: 9, page: 1, filters },
    });
    await wrapper.get("[data-testid='ov-target-case-next']").trigger("click");
    expect(wrapper.emitted("update:page")?.at(-1)).toEqual([2]);
    expect(wrapper.get("[data-testid='ov-target-case-pager']").text()).toContain(
      "第 1 / 2 页",
    );

    const empty = mount(PotentialCaseTable, {
      props: { wid: "ws-1", items: [], total: 0, filters },
    });
    expect(empty.find("[data-testid='ov-target-case-empty']").exists()).toBe(true);

    const filtered = mount(PotentialCaseTable, {
      props: {
        wid: "ws-1",
        items: [],
        total: 0,
        filters: { ...filters, caseState: "unanalyzed" },
      },
    });
    expect(filtered.text()).toContain("没有符合条件的潜在 bad case");
  });
});
