// @vitest-environment jsdom

import { mount, type VueWrapper } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import type { BadCase } from "@harness/contracts";

import { badCaseFixture } from "../../../test/badCases";
import ProblemDescription from "./ProblemDescription.vue";

const variants: Array<{ state: string; problem: BadCase }> = [
  {
    state: "unanalyzed",
    problem: badCaseFixture({
      badCaseId: "case-unanalyzed",
      title: "尚未归因",
      reason: "这一条问题还没有完成归因分析，描述正文仍然完整保留。",
    }),
  },
  {
    state: "analyzed_nonissue",
    problem: badCaseFixture({
      badCaseId: "case-nonissue",
      title: "响应可追溯",
      reason: "traceable response: 每条结论都能回指到来源。",
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
  },
  {
    state: "analyzed_issue",
    problem: badCaseFixture({
      badCaseId: "case-issue",
      title: "索引读取失败",
      reason: "index read failed: 读取检索索引时抛出 ENOENT。",
      objectType: "agent",
      objectName: "Explore",
      metaData: { file: "src/index.ts", line: 42 },
      analysis: {
        probeId: "probe-error",
        attributeType: "error",
        displayState: "analyzed_issue_error",
        result: { summary: "The index file was missing." },
        status: "analyzed_issue",
      },
    }),
  },
];

/**
 * Collect the description blocks in rendered document order.
 * @param wrapper Mounted problem description.
 * @returns Block class names without modifiers.
 */
function blockOrder(wrapper: VueWrapper): string[] {
  return wrapper
    .findAll(
      ".problem-heading, .problem-detail, .facts, .association, .diagnostic",
    )
    .map((node) => node.element.className.split(" ")[0] ?? "");
}

describe("ProblemDescription", () => {
  it.each(variants)(
    "renders the short title and the full description for $state",
    ({ problem }) => {
      const wrapper = mount(ProblemDescription, {
        props: { problem, index: 2 },
      });

      expect(wrapper.get(".problem-title").text()).toBe(problem.title);
      expect(wrapper.get(".problem-title").text()).not.toBe(problem.reason);
      expect(wrapper.get("[data-testid='problem-detail']").text()).toBe(
        problem.reason,
      );
      expect(wrapper.get(".problem-number").text()).toBe("#2");
    },
  );

  it("keeps the heading chips and orders body, facts and association after it", () => {
    const wrapper = mount(ProblemDescription, {
      props: { problem: variants[2]!.problem, index: 2 },
    });

    expect(blockOrder(wrapper)).toEqual([
      "problem-heading",
      "problem-detail",
      "facts",
      "association",
    ]);
    expect(wrapper.get(".problem-title").attributes("id")).toBe(
      "problem-description-title",
    );
    expect(wrapper.get(".state-chip").text()).toBe("是问题-错误");
    expect(wrapper.get(".report-id").text()).toBe("probe-er");
    expect(wrapper.find(".degraded-chip").exists()).toBe(false);
  });

  it("keeps the degraded chip and diagnostic without collapsing the two text levels", () => {
    const wrapper = mount(ProblemDescription, {
      props: {
        problem: badCaseFixture({
          badCaseId: "case-degraded",
          title: "数据漂移",
          reason: "外部上报缺少 title，当前以派生标题展示问题。",
          degraded: true,
          diagnosticCode: "BAD_CASE_TITLE_MISSING",
        }),
        index: null,
      },
    });

    expect(blockOrder(wrapper)).toEqual([
      "problem-heading",
      "problem-detail",
      "association",
      "diagnostic",
    ]);
    expect(wrapper.get(".problem-title").text()).toBe("数据漂移");
    expect(wrapper.get(".problem-detail").text()).toBe(
      "外部上报缺少 title，当前以派生标题展示问题。",
    );
    expect(wrapper.get(".degraded-chip").text()).toBe("数据降级");
    expect(wrapper.find(".problem-number").exists()).toBe(false);
  });
});
