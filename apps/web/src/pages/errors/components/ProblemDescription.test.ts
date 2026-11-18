// @vitest-environment jsdom

import { mount, type VueWrapper } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import type { AttributionItem, BadCase } from "@harness/contracts";

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

function attributionFixture(
  overrides: Partial<AttributionItem> = {},
): AttributionItem {
  return {
    attributionId: "probe-error",
    badCaseId: "case-issue",
    objectType: "agent",
    objectName: "Explore",
    objectVersion: "synthetic-1",
    conclusion: "attributed",
    category: "error",
    confidence: 0.86,
    runId: null,
    isCached: false,
    reusedCount: 0,
    createdAt: "2026-10-20T09:03:30+08:00",
    updatedAt: "2026-10-20T09:03:30+08:00",
    ...overrides,
  };
}

/**
 * Collect the description blocks in rendered document order.
 * @param wrapper Mounted problem description.
 * @returns Block class names without modifiers.
 */
function blockOrder(wrapper: VueWrapper): string[] {
  return wrapper
    .findAll(
      ".problem-heading, .problem-meta, .problem-detail, .facts, .association, .diagnostic",
    )
    .map((node) => node.element.className.split(" ")[0] ?? "");
}

describe("ProblemDescription", () => {
  it.each(variants)(
    "renders the short title and the full description for $state",
    ({ problem }) => {
      const wrapper = mount(ProblemDescription, {
        props: { wid: "ws-test", problem, index: 2 },
      });

      expect(wrapper.get(".problem-title").text()).toBe(problem.title);
      expect(wrapper.get(".problem-title").text()).not.toBe(problem.reason);
      expect(wrapper.get("[data-testid='problem-detail']").text()).toBe(
        problem.reason,
      );
      expect(wrapper.get(".problem-number").text()).toBe("#2");
    },
  );

  it("keeps the heading and meta before the body, facts and association", () => {
    const wrapper = mount(ProblemDescription, {
      props: { wid: "ws-test", problem: variants[2]!.problem, index: 2 },
    });

    expect(blockOrder(wrapper)).toEqual([
      "problem-heading",
      "problem-meta",
      "problem-detail",
      "facts",
      "association",
    ]);
    expect(wrapper.get(".problem-title").attributes("id")).toBe(
      "problem-description-title",
    );
    expect(wrapper.get(".type-badge").text()).toBe("self");
    expect(wrapper.get(".meta-chip").text()).toContain("Explore");
    expect(wrapper.find(".degraded-chip").exists()).toBe(false);
  });

  it("summarizes generated attributions and opens the analysis tab on request", async () => {
    const wrapper = mount(ProblemDescription, {
      props: {
        wid: "ws-test",
        problem: { ...variants[2]!.problem, attributionCount: 3 },
        index: 2,
        attributions: [
          attributionFixture(),
          attributionFixture({
            attributionId: "probe-two",
            conclusion: "non_target",
            category: null,
          }),
          attributionFixture({ attributionId: "probe-three" }),
        ],
      },
    });

    const summary = wrapper.get("[data-testid='problem-attribution-summary']");
    expect(summary.text()).toContain("已生成 3 条归因");
    expect(summary.text()).toContain("2 可归因");
    expect(summary.text()).toContain("1 非该对象");
    await summary.trigger("click");
    expect(wrapper.emitted("openAttribution")).toHaveLength(1);
  });

  it("keeps an explicitly unanalyzed case distinct from a non-target conclusion", () => {
    const wrapper = mount(ProblemDescription, {
      props: {
        wid: "ws-test",
        problem: { ...variants[0]!.problem, attributionCount: 0 },
        index: 1,
      },
    });

    expect(
      wrapper.get("[data-testid='problem-attribution-summary']").text(),
    ).toBe("尚未归因");
    expect(wrapper.text()).not.toContain("非该对象问题");
  });

  it("keeps the degraded chip and diagnostic without collapsing the two text levels", () => {
    const wrapper = mount(ProblemDescription, {
      props: {
        wid: "ws-test",
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
      "problem-meta",
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

  it("renders the description as safe Markdown", () => {
    const wrapper = mount(ProblemDescription, {
      props: {
        wid: "ws-test",
        problem: badCaseFixture({
          badCaseId: "case-markdown",
          title: "Markdown 描述",
          reason: [
            "**result_status** = `unresolved`",
            "",
            "**F2P 失败**",
            "- `test_cirs_its_topo`",
            "- `test_its_straight_overhead`",
            "",
            "line one",
            "line two",
            "[source](https://example.com)",
          ].join("\n"),
        }),
        index: null,
      },
    });

    const detail = wrapper.get("[data-testid='problem-detail']");
    expect(detail.element.innerHTML).toContain("<ul>");
    expect(detail.element.innerHTML).toContain("<li>");
    expect(detail.findAll("code").map((node) => node.text())).toEqual(
      expect.arrayContaining(["unresolved", "test_cirs_its_topo"]),
    );
    expect(detail.findAll("strong").map((node) => node.text())).toEqual(
      expect.arrayContaining(["result_status", "F2P 失败"]),
    );
    expect(detail.element.innerHTML).toContain("<br>");
    const link = detail.get("a");
    expect(link.attributes("href")).toBe("https://example.com");
    expect(link.attributes("target")).toBe("_blank");
    expect(link.attributes("rel")).toBe("noopener noreferrer");
  });

  it("does not render raw HTML from the description", () => {
    const wrapper = mount(ProblemDescription, {
      props: {
        wid: "ws-test",
        problem: badCaseFixture({
          badCaseId: "case-raw-html",
          title: "原始 HTML",
          reason: '<img src=x onerror="alert(1)"><script>alert(2)</script>',
        }),
        index: null,
      },
    });

    const detail = wrapper.get("[data-testid='problem-detail']");
    expect(detail.find("img").exists()).toBe(false);
    expect(detail.find("script").exists()).toBe(false);
    expect(detail.text()).toContain("<img");
    expect(detail.text()).toContain("<script>");
  });

  it("does not load Markdown images from the description", () => {
    const wrapper = mount(ProblemDescription, {
      props: {
        wid: "ws-test",
        problem: badCaseFixture({
          badCaseId: "case-image",
          title: "图片描述",
          reason: "![tracking pixel](https://example.com/pixel.png)",
        }),
        index: null,
      },
    });

    const detail = wrapper.get("[data-testid='problem-detail']");
    expect(detail.find("img").exists()).toBe(false);
    expect(detail.element.innerHTML).not.toContain("pixel.png");
    expect(detail.text()).toContain("tracking pixel");
  });
});
