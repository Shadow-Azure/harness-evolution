import { describe, expect, it } from "vitest";

import {
  badCaseFactEntries,
  badCaseState,
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

  it("renders at most three compact metadata facts", () => {
    const facts = badCaseFactEntries({
      file: "apps/server/src/search/index.ts",
      line: 142,
      error: "x".repeat(90),
      ignored: "fourth",
    });

    expect(facts).toHaveLength(3);
    expect(facts[0]).toEqual({
      key: "file",
      value: "apps/server/src/search/index.ts",
    });
    expect(facts[1]).toEqual({ key: "line", value: "142" });
    expect(facts[2]).toEqual({ key: "error", value: `${"x".repeat(71)}…` });
    expect(badCaseFactEntries(null)).toEqual([]);
  });
});
