// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { BadCase } from "@harness/contracts";

import { badCaseFixture } from "../../test/badCases";
import BadCaseList from "./BadCaseList.vue";

const originalScrollIntoView = Object.getOwnPropertyDescriptor(
  HTMLElement.prototype,
  "scrollIntoView",
);

afterEach(() => {
  if (originalScrollIntoView) {
    Object.defineProperty(
      HTMLElement.prototype,
      "scrollIntoView",
      originalScrollIntoView,
    );
    return;
  }
  delete (HTMLElement.prototype as {
    scrollIntoView?: typeof HTMLElement.prototype.scrollIntoView;
  }).scrollIntoView;
});

const fiveStates = [
  badCaseFixture({
    badCaseId: "case-unanalyzed",
    reason: "pending attribution",
    analysis: {
      probeId: null,
      attributeType: null,
      displayState: "unanalyzed",
      result: null,
      status: "unanalyzed",
    },
  }),
  badCaseFixture({
    badCaseId: "case-nonissue",
    reason: "traceable response",
    analysis: {
      probeId: "probe-nonissue",
      attributeType: null,
      displayState: "analyzed_nonissue",
      result: {
        reason: "Every claim has a source.",
        reasoning: ["A source is present."],
      },
      status: "analyzed_nonissue",
    },
  }),
  badCaseFixture({
    badCaseId: "case-model",
    reason: "model over-scanned",
    analysis: {
      probeId: "probe-model",
      attributeType: "model",
      displayState: "analyzed_issue_model",
      result: { summary: "The model exceeded its budget." },
      status: "analyzed_issue",
    },
  }),
  badCaseFixture({
    badCaseId: "case-prompt",
    reason: "prompt missed validation",
    analysis: {
      probeId: "probe-prompt",
      attributeType: "prompt",
      displayState: "analyzed_issue_prompt",
      result: { summary: "The prompt omitted validation." },
      status: "analyzed_issue",
    },
  }),
  badCaseFixture({
    badCaseId: "case-error",
    reason: "index read failed",
    metaData: {
      file: "apps/server/src/search/index.ts",
      line: 142,
      error: "ENOENT",
    },
    analysis: {
      probeId: "probe-error",
      attributeType: "error",
      displayState: "analyzed_issue_error",
      result: { summary: "The index file was missing." },
      status: "analyzed_issue",
    },
  }),
] satisfies BadCase[];

describe("BadCaseList", () => {
  it("renders all five labels, summaries and stable short IDs", () => {
    const wrapper = mount(BadCaseList, {
      props: { problems: fiveStates },
    });

    expect(wrapper.get("[data-testid='problem-list']").text()).toContain(
      "5 条",
    );
    expect(wrapper.text()).toContain("未分析");
    expect(wrapper.text()).toContain("非问题");
    expect(wrapper.text()).toContain("是问题-模型问题");
    expect(wrapper.text()).toContain("是问题-prompt缺失某些提示词");
    expect(wrapper.text()).toContain("是问题-错误");
    expect(wrapper.text()).toContain("尚未完成归因分析");
    expect(wrapper.text()).toContain("Every claim has a source.");
    expect(wrapper.text()).toContain("The model exceeded its budget.");
    expect(wrapper.text()).toContain("file=apps/server/src/search/index.ts");
    expect(wrapper.get(".state-chip.purple").text()).toBe("是问题-模型问题");
    expect(wrapper.get(".state-chip.orange").text()).toBe(
      "是问题-prompt缺失某些提示词",
    );
    expect(wrapper.get(".state-chip.red").text()).toBe("是问题-错误");

    const firstId = wrapper.get(
      "#problem-row-case-unanalyzed .problem-id",
    );
    expect(firstId.text()).toBe("case-una");
    expect(firstId.attributes("title")).toBe("case-unanalyzed");
    expect(firstId.attributes("href")).toBe(
      "/sessions/root-1/errors?case=case-unanalyzed&tab=desc",
    );
    expect(firstId.attributes("target")).toBe("_blank");
    expect(firstId.attributes("rel")).toBe("noopener noreferrer");
    expect(firstId.attributes("aria-label")).toBe(
      "问题 case-una，在新窗口打开问题描述",
    );
  });

  it("keeps degraded problems visible with an explicit diagnostic label", () => {
    const wrapper = mount(BadCaseList, {
      props: {
        problems: [
          badCaseFixture({
            badCaseId: "case-degraded",
            degraded: true,
            diagnosticCode: "BAD_CASE_DISPLAY_STATE_UNKNOWN",
          }),
        ],
      },
    });

    expect(wrapper.get("[data-bad-case-id='case-degraded']").text()).toContain(
      "数据降级",
    );
  });

  it("emits the real badCaseId and gives every row one active source of truth", async () => {
    const wrapper = mount(BadCaseList, {
      props: {
        problems: fiveStates,
        activeBadCaseId: "case-prompt",
      },
    });

    const items = wrapper.findAll("[role='listitem']");
    expect(items).toHaveLength(5);
    expect(items[0]?.element.tagName).toBe("DIV");

    const buttons = wrapper.findAll("button.problem-row");
    expect(buttons).toHaveLength(5);
    expect(buttons[0]?.attributes("role")).toBeUndefined();

    expect(
      wrapper.findAll("[data-bad-case-id]").filter(
        (row) => row.attributes("aria-pressed") === "true",
      ),
    ).toHaveLength(1);
    expect(
      wrapper.get("[data-bad-case-id='case-prompt']").classes(),
    ).toContain("active");
    const rows = wrapper.findAll(".problem-row");
    expect(rows.every((row) => row.element.tagName === "BUTTON")).toBe(true);
    expect(rows.every((row) => row.attributes("role") === undefined)).toBe(true);
    expect(
      wrapper
        .get("[data-bad-case-id='case-prompt']")
        .attributes("aria-pressed"),
    ).toBe("true");

    await wrapper.get("[data-bad-case-id='case-error']").trigger("click");

    expect(wrapper.emitted("select")).toEqual([["case-error"]]);
  });

  it("keeps the ID deep link independent from card selection", async () => {
    const wrapper = mount(BadCaseList, {
      props: { problems: fiveStates },
    });

    const idLink = wrapper.get(
      "#problem-row-case-error .problem-id",
    );
    expect(idLink.element.tagName).toBe("A");
    expect(idLink.text()).toBe("case-err");
    expect(idLink.attributes("title")).toBe("case-error");
    expect(idLink.attributes("target")).toBe("_blank");
    expect(idLink.attributes("rel")).toBe("noopener noreferrer");
    expect(idLink.attributes("aria-label")).toBe(
      "问题 case-err，在新窗口打开问题描述",
    );

    await idLink.trigger("click");
    expect(wrapper.emitted("select")).toBeUndefined();

    await wrapper.get("[data-bad-case-id='case-error']").trigger("click");
    expect(wrapper.emitted("select")).toEqual([["case-error"]]);
  });

  it("groups compact card status and target below the reason", () => {
    const wrapper = mount(BadCaseList, {
      props: { problems: fiveStates, compact: true },
    });

    const card = wrapper.get("#problem-row-case-error");
    expect(card.get(".problem-card-main").text()).not.toContain("是问题-错误");
    expect(card.get(".problem-card-secondary").text()).toContain("是问题-错误");
    expect(card.get(".problem-card-secondary").text()).toContain(
      "skill · deep-research",
    );
  });

  it("links analyzed issue cards to their attribution report", async () => {
    const wrapper = mount(BadCaseList, {
      props: { problems: fiveStates, compact: true },
    });

    const reportLink = wrapper.get(
      "#problem-row-case-error .report-id",
    );
    expect(reportLink.text()).toBe("probe-er");
    expect(reportLink.attributes("title")).toBe("probe-error");
    expect(reportLink.attributes("href")).toBe(
      "/sessions/root-1/errors?case=case-error&tab=attr",
    );
    expect(reportLink.attributes("target")).toBe("_blank");
    expect(reportLink.attributes("rel")).toBe("noopener noreferrer");
    expect(reportLink.attributes("aria-label")).toBe(
      "归因报告 probe-er，在新窗口打开归因分析",
    );
    expect(reportLink.element.closest("button")).toBeNull();
    expect(
      wrapper.find("#problem-row-case-unanalyzed .report-id").exists(),
    ).toBe(false);
    expect(
      wrapper.find("#problem-row-case-nonissue .report-id").exists(),
    ).toBe(false);

    await reportLink.trigger("click");
    expect(wrapper.emitted("select")).toBeUndefined();
  });

  it("scrolls the active row into view when graph selection changes", async () => {
    const scrollIntoView = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });
    const wrapper = mount(BadCaseList, {
      props: { problems: fiveStates },
      attachTo: document.body,
    });

    await wrapper.setProps({ activeBadCaseId: "case-model" });
    await nextTick();

    expect(scrollIntoView).toHaveBeenCalledWith({
      behavior: "auto",
      block: "nearest",
    });
  });

  it("renders loading, empty, and retryable error states independently", async () => {
    const loading = mount(BadCaseList, {
      props: { problems: [], loading: true },
    });
    expect(loading.get("[role='status']").attributes("aria-label")).toBe(
      "正在读取问题",
    );

    const empty = mount(BadCaseList, {
      props: { problems: [] },
    });
    expect(empty.text()).toContain("暂无问题");

    const failed = mount(BadCaseList, {
      props: { problems: [], error: new Error("offline") },
    });
    expect(failed.text()).toContain("问题列表读取失败");
    await failed.get("button").trigger("click");
    expect(failed.emitted("retry")).toEqual([[]]);
  });
});
