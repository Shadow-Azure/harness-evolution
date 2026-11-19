import { describe, expect, it } from "vitest";

import type { SessionAgent, SessionEvent, SessionTree } from "@harness/contracts";

import { demoNestedTree } from "../tree/fixtures/demo-nested";
import { buildLaneModel } from "./laneModel";
import { LANE_MAIN_ROW_H, LANE_ROW_H, LANE_TOP } from "../types";

function agent(overrides: Partial<SessionAgent> = {}): SessionAgent {
  return {
    agentId: "main",
    parentAgentId: null,
    kind: "main",
    agentType: null,
    taskKind: null,
    spawnDepth: 0,
    label: "主会话",
    desc: "主会话",
    lines: 100,
    messagesCount: 100,
    toolUseId: null,
    skillName: null,
    teamName: null,
    executionOutcome: "legacy_unknown",
    events: [],
    ...overrides,
  };
}

function event(overrides: Partial<SessionEvent> = {}): SessionEvent {
  return {
    kind: "agent",
    line: 10,
    messageOffset: 10,
    name: "agent",
    desc: "agent",
    toolUseId: null,
    ...overrides,
  };
}

function tree(agents: SessionAgent[], badCases: SessionTree["badCases"] = []): SessionTree {
  return {
    sessionId: "lane-test",
    runtimeKey: "claude-code",
    agents,
    badCases,
  };
}

describe("buildLaneModel paths and depth", () => {
  it("labels the main chain A1 and nested invocations A1.1 / A1.1.1", () => {
    const model = buildLaneModel(demoNestedTree);
    const paths = new Map(model.lanes.map((lane) => [lane.id, lane.path]));

    expect(paths.get("main")).toBe("A1");
    expect(paths.get("agent-a")).toBe("A1.1");
    expect(paths.get("agent-c")).toBe("A1.1.1");
    expect(paths.get("workflow-1")).toBe("A1.2");
    expect(paths.get("agent-b")).toBe("A1.4");

    const nested = model.lanes.find((lane) => lane.id === "agent-c");
    expect(nested?.depth).toBe(2);
    expect(nested?.parentId).toBe("agent-a");
    expect(model.diagnostics).toEqual([]);
  });

  it("keeps every lane expanded, including a 56-subagent session", () => {
    const extras = Array.from({ length: 56 }, (_, index) =>
      agent({
        agentId: `sub-${index + 1}`,
        parentAgentId: "main",
        kind: "subagent",
        label: `任务 ${index + 1}`,
        desc: `任务 ${index + 1}`,
        lines: 5,
        toolUseId: `tool-${index + 1}`,
      }),
    );
    const main = agent({
      events: extras.map((child, index) =>
        event({
          line: index + 1,
          messageOffset: index + 1,
          name: child.label,
          desc: child.desc,
          toolUseId: child.toolUseId,
        }),
      ),
    });
    const model = buildLaneModel(tree([main, ...extras]));

    expect(model.lanes).toHaveLength(57);
    expect(model.lanes.every((lane) => lane.path !== "F1")).toBe(true);
    expect(model.height).toBe(LANE_TOP + LANE_MAIN_ROW_H + 56 * LANE_ROW_H);
    expect(Math.min(...model.lanes.map((lane) => lane.depth))).toBe(0);
    expect(Math.max(...model.lanes.map((lane) => lane.depth))).toBe(1);
  });

  it("falls back to the main lane for orphan agents and reports it", () => {
    const model = buildLaneModel(
      tree([
        agent(),
        agent({
          agentId: "orphan",
          parentAgentId: "missing",
          kind: "subagent",
          label: "孤儿",
          toolUseId: "tool-orphan",
        }),
      ]),
    );
    expect(model.lanes.find((lane) => lane.id === "orphan")?.parentId).toBe("main");
    expect(model.diagnostics.map((item) => item.code)).toContain("ORPHAN_PARENT");
  });

  it("returns an empty model when the main Agent is missing", () => {
    const model = buildLaneModel(
      tree([
        agent({
          agentId: "sub",
          parentAgentId: null,
          kind: "subagent",
        }),
      ]),
    );
    expect(model.lanes).toEqual([]);
    expect(model.caseMarkers).toEqual([]);
    expect(model.diagnostics.map((item) => item.code)).toEqual(["MISSING_MAIN"]);
  });
});

describe("buildLaneModel intervals", () => {
  it("covers the full log axis with contiguous, non-overlapping main bars", () => {
    const model = buildLaneModel(demoNestedTree);
    const main = model.lanes[0]!;
    expect(main.start).toBe(0);
    expect(main.end).toBe(100);
    expect(main.bars[0]!.start).toBe(0);
    expect(main.bars.at(-1)!.end).toBe(100);
    for (let index = 1; index < main.bars.length; index += 1) {
      expect(main.bars[index]!.start).toBeGreaterThanOrEqual(
        main.bars[index - 1]!.end - 0.001,
      );
    }
    expect(main.bars.some((bar) => bar.kind === "gap")).toBe(true);
    expect(main.bars.filter((bar) => bar.rail).map((bar) => bar.lo)).toEqual([
      20, 50, 60, 80,
    ]);
  });

  it("merges adjacent triggers into one multi-action bar", () => {
    const model = buildLaneModel(
      tree([
        agent({
          lines: 10,
          events: [
            event({ line: 3, messageOffset: 3, name: "a", toolUseId: "a" }),
            event({ line: 4, messageOffset: 4, name: "b", toolUseId: "b" }),
          ],
        }),
      ]),
    );
    const rail = model.lanes[0]!.bars.filter((bar) => bar.rail);
    expect(rail).toHaveLength(1);
    expect(rail[0]!.label).toBe("2 个 agent");
    expect(rail[0]!.lo).toBe(3);
    expect(rail[0]!.hi).toBe(4);
  });

  it("keeps bars inside each lane non-overlapping and expresses concurrency across lanes", () => {
    const model = buildLaneModel(demoNestedTree);
    for (const lane of model.lanes) {
      const bars = [...lane.bars].sort((left, right) => left.start - right.start);
      for (let index = 1; index < bars.length; index += 1) {
        expect(bars[index]!.start).toBeGreaterThanOrEqual(
          bars[index - 1]!.end - 0.001,
        );
      }
    }
    expect(model.concurrencyBands).toHaveLength(1);
    const subLanes = model.lanes.filter((lane) => lane.depth > 0);
    expect(model.concurrencyBands[0]!.left).toBe(
      Math.min(...subLanes.map((lane) => lane.start)),
    );
    expect(model.concurrencyBands[0]!.right).toBe(
      Math.max(...subLanes.map((lane) => lane.end)),
    );
  });

  it("scales sub-lane width by log lines and caps the longest at 42%", () => {
    const main = agent({
      lines: 100,
      events: [event({ line: 10, toolUseId: "a" }), event({ line: 20, toolUseId: "b" })],
    });
    const short = agent({
      agentId: "short",
      parentAgentId: "main",
      kind: "subagent",
      lines: 10,
      toolUseId: "a",
      label: "short",
    });
    const long = agent({
      agentId: "long",
      parentAgentId: "main",
      kind: "subagent",
      lines: 100,
      toolUseId: "b",
      label: "long",
    });
    const model = buildLaneModel(tree([main, short, long]));
    const shortLane = model.lanes.find((lane) => lane.id === "short")!;
    const longLane = model.lanes.find((lane) => lane.id === "long")!;
    expect(longLane.end - longLane.start).toBeCloseTo(42, 1);
    expect(shortLane.end - shortLane.start).toBeCloseTo(4.2, 1);
  });
});

describe("buildLaneModel bad-case markers", () => {
  it("anchors every case to its trigger line and preserves all branches when selected", () => {
    const model = buildLaneModel(demoNestedTree, "case-discovery");
    const selected = model.caseMarkers.find(
      (marker) => marker.badCaseId === "case-discovery",
    );
    expect(selected?.line).toBe(20);
    expect(selected?.selected).toBe(true);
    expect(selected?.inGap).toBe(false);
    expect(selected?.barId).not.toBeNull();
    expect(model.lanes).toHaveLength(demoNestedTree.agents.length);
    expect(model.caseMarkers).toHaveLength(demoNestedTree.badCases.length);
    expect(
      model.lanes.find((lane) => lane.id === "agent-a")?.cases.map(
        (marker) => marker.badCaseId,
      ),
    ).toEqual(["case-self-skill", "case-self-agent"]);
  });

  it("marks cases landing in a no-trigger gap and explains the nearest triggers", () => {
    const model = buildLaneModel(demoNestedTree, "case-self-skill");
    const marker = model.caseMarkers.find(
      (item) => item.badCaseId === "case-self-skill",
    )!;
    expect(marker.line).toBe(10);
    expect(marker.inGap).toBe(true);
    expect(marker.gapNote).toContain("无触发区间");
    expect(marker.gapNote).toContain("→ L20");
  });

  it("falls back to line 1 for a missing anchor event", () => {
    const model = buildLaneModel(demoNestedTree);
    const marker = model.caseMarkers.find(
      (item) => item.badCaseId === "case-fallback",
    )!;
    expect(marker.line).toBe(1);
    expect(marker.inGap).toBe(true);
  });

  it("pins a post-process marker at the end without indexing the sentinel event", () => {
    const main = agent({
      events: [event({ line: 10, messageOffset: 10 })],
    });
    const postProcess = {
      ...demoNestedTree.badCases[0]!,
      badCaseId: "case-post-process",
      anchor: {
        agentId: "main",
        eventIndex: 2_147_483_647,
        kind: "post_process" as const,
      },
    };
    const model = buildLaneModel(tree([main], [postProcess]));
    const marker = model.caseMarkers[0]!;

    expect(marker.anchorLabel).toBe("后处理");
    expect(marker.line).toBe(100);
    expect(marker.x).toBeGreaterThan(90);
    expect(JSON.stringify(marker)).not.toContain("2147483647");
  });

  it("keeps node and unknown markers at the host without a huge index", () => {
    const main = agent();
    const badCases = (["node", "unknown"] as const).map((kind) => ({
      ...demoNestedTree.badCases[0]!,
      badCaseId: `case-${kind}`,
      anchor: { agentId: "main", eventIndex: -1, kind },
    }));
    const model = buildLaneModel(tree([main], badCases));

    expect(model.caseMarkers.map((marker) => marker.line)).toEqual([1, 1]);
    expect(model.caseMarkers.map((marker) => marker.anchorLabel)).toEqual([
      null,
      null,
    ]);
    expect(JSON.stringify(model.caseMarkers)).not.toContain("2147483647");
  });
});
