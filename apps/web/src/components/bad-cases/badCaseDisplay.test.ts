import { describe, expect, it } from "vitest";

import {
  badCaseAnchorPresentation,
  badCaseFactEntries,
  badCaseState,
} from "./badCaseDisplay";

describe("bad-case display", () => {
  it.each([
    ["unanalyzed", "未分析", "neutral"],
    ["analyzed_nonissue", "非问题", "green"],
    ["analyzed_issue_model", "是问题-模型问题", "purple"],
    ["analyzed_issue_prompt", "是问题-提示词问题", "orange"],
    ["analyzed_issue_error", "是问题-错误", "red"],
    ["analyzed_issue_flow", "是问题-流程", "blue"],
    ["analyzed_issue_context", "是问题-上下文", "green"],
  ] as const)(
    "maps %s to the prototype label and tone",
    (displayState, label, tone) => {
      expect(badCaseState(displayState)).toEqual({ label, tone });
    },
  );

  it("labels non-event anchors without exposing the INT_MAX sentinel", () => {
    expect(
      badCaseAnchorPresentation({
        agentId: "agent-1",
        eventIndex: 2_147_483_647,
        kind: "post_process",
      }),
    ).toMatchObject({ label: "后处理", tone: "orange" });
    expect(
      badCaseAnchorPresentation({
        agentId: "agent-1",
        eventIndex: -1,
        kind: "unknown",
      }),
    ).toMatchObject({ label: "锚点未知", tone: "neutral" });
    expect(
      badCaseAnchorPresentation({
        agentId: "agent-1",
        eventIndex: 0,
        kind: "event",
      }),
    ).toBeNull();
    expect(
      badCaseAnchorPresentation({
        agentId: "agent-1",
        eventIndex: -1,
        kind: "node",
      }),
    ).toBeNull();
  });

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
