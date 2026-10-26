import { describe, expect, it } from "vitest";

import { badCaseFixture } from "../../test/badCases";
import {
  badCaseFacts,
  badCaseState,
  badCaseSummary,
} from "./badCaseDisplay";

describe("bad-case display", () => {
  it.each([
    ["unanalyzed", "未分析", "neutral"],
    ["analyzed_nonissue", "非问题", "green"],
    ["analyzed_issue_model", "是问题-模型问题", "purple"],
    [
      "analyzed_issue_prompt",
      "是问题-prompt缺失某些提示词",
      "orange",
    ],
    ["analyzed_issue_error", "是问题-错误", "red"],
  ] as const)(
    "maps %s to the prototype label and tone",
    (displayState, label, tone) => {
      expect(badCaseState(displayState)).toEqual({ label, tone });
    },
  );

  it("uses the public issue summary for analyzed issues", () => {
    const problem = badCaseFixture({
      analysis: {
        probeId: "probe-1",
        attributeType: "model",
        displayState: "analyzed_issue_model",
        result: { summary: "The model exceeded its scanning budget." },
        status: "analyzed_issue",
      },
    });

    expect(badCaseSummary(problem)).toBe(
      "The model exceeded its scanning budget.",
    );
  });

  it("uses the non-issue reason and an explicit unanalyzed message", () => {
    expect(
      badCaseSummary(
        badCaseFixture({
          analysis: {
            probeId: "probe-2",
            attributeType: null,
            displayState: "analyzed_nonissue",
            result: {
              reason: "The output was traceable.",
              reasoning: ["Every claim had a source."],
            },
            status: "analyzed_nonissue",
          },
        }),
      ),
    ).toBe("The output was traceable.");
    expect(badCaseSummary(badCaseFixture())).toBe("尚未完成归因分析");
  });

  it("renders at most three compact metadata facts", () => {
    const facts = badCaseFacts({
      file: "apps/server/src/search/index.ts",
      line: 142,
      error: "x".repeat(90),
      ignored: "fourth",
    });

    expect(facts).toHaveLength(3);
    expect(facts[0]).toBe("file=apps/server/src/search/index.ts");
    expect(facts[1]).toBe("line=142");
    expect(facts[2]).toBe(`error=${"x".repeat(71)}…`);
    expect(badCaseFacts(null)).toEqual([]);
  });
});
