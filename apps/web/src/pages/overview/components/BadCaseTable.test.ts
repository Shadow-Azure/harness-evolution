// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import BadCaseTable from "./BadCaseTable.vue";

function row(index: number) {
  return {
    badCaseId: `BC-HC-00${index}`,
    sessionId: `session-${index}`,
    objectName: "deep-research",
    badCaseType: index % 2 === 0 ? ("self" as const) : ("discovery" as const),
    badCaseTypeLabel: index % 2 === 0 ? "自身存在问题" : "发现前置步骤问题",
    title: `Case title ${index}`,
    triggerAt: `2026-11-0${index}T08:00:00+08:00`,
    createdAt: `2026-11-0${index}T09:00:00+08:00`,
    attributionCount: index,
  };
}

function mountTable(overrides: Record<string, unknown> = {}) {
  return mount(BadCaseTable, {
    props: {
      wid: "ws-test",
      items: [row(1), row(2)],
      total: 2,
      page: 1,
      pageSize: 8,
      type: "all",
      filtered: false,
      loading: false,
      error: null,
      ...overrides,
    },
  });
}

describe("overview bad-case table", () => {
  it("renders eight-row pages with a deep link per case", () => {
    const wrapper = mountTable();

    const rows = wrapper.findAll("[data-testid='ov-case-row']");
    expect(rows).toHaveLength(2);
    const link = wrapper.get("[data-testid='ov-case-link-BC-HC-001']");
    expect(link.attributes("href")).toBe(
      "/workspaces/ws-test/sessions/session-1/errors?case=BC-HC-001&tab=desc",
    );
    expect(link.attributes("target")).toBe("_blank");
    expect(link.attributes("rel")).toBe("noopener");
    expect(rows[0]?.text()).toContain("Case title 1");
    expect(rows[0]?.text()).toContain("发现前置步骤问题");
    expect(rows[0]?.text()).toContain("deep-research");
  });

  it("paginates at the page size and disables boundary buttons", async () => {
    const wrapper = mountTable({
      items: [row(1)],
      total: 17,
      page: 2,
      type: "self",
    });

    expect(wrapper.get("[data-testid='ov-case-total']").text()).toContain("共 17 条");
    expect(wrapper.get("[data-testid='ov-pager']").text()).toContain("第 2 / 3 页");

    await wrapper.get("[data-testid='ov-page-next']").trigger("click");
    await wrapper.get("[data-testid='ov-page-prev']").trigger("click");
    expect(wrapper.emitted("update:page")).toEqual([[3], [1]]);
    expect(wrapper.get("[data-testid='ov-type-chip']").text()).toContain(
      "自身存在问题",
    );
    await wrapper.get("[data-testid='ov-type-clear']").trigger("click");
    expect(wrapper.emitted("clear-filters")).toHaveLength(1);
  });

  it("distinguishes an empty workspace from a filter miss", async () => {
    const unfiltered = mountTable({ items: [], total: 0 });
    expect(unfiltered.get("[data-testid='ov-case-empty']").text()).toContain(
      "这个空间还没有 bad case",
    );
    expect(
      unfiltered.find("[data-testid='ov-case-empty-clear']").exists(),
    ).toBe(false);
    expect(unfiltered.find("[data-testid='ov-pager']").exists()).toBe(false);

    const filtered = mountTable({ items: [], total: 0, filtered: true });
    expect(filtered.get("[data-testid='ov-case-empty']").text()).toContain(
      "当前筛选没有命中",
    );
    await filtered.get("[data-testid='ov-case-empty-clear']").trigger("click");
    expect(filtered.emitted("clear-filters")).toHaveLength(1);
  });

  it("renders the loading skeleton and the retryable block error", async () => {
    const loading = mountTable({ loading: true, items: [] });
    expect(loading.find("[data-testid='ov-case-loading']").exists()).toBe(true);

    const failed = mountTable({ error: new Error("boom"), items: [] });
    expect(failed.find("[data-testid='ov-case-error']").exists()).toBe(true);
    await failed.get("button").trigger("click");
    expect(failed.emitted("retry")).toHaveLength(1);
  });
});
