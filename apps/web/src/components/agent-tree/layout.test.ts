import { describe, expect, it } from "vitest";

import type { SessionAgent, SessionTree } from "@harness/contracts";

import { demoCoreTree, demoNestedTree } from "./fixtures/demo-nested";
import {
  AGENT_BOX_H,
  BOX_EDGE,
  BOX_PAD,
  FONT_AGENT_LABEL,
  INDENT,
  MIN_STEP,
  ROW_STEP,
  buildGraph,
  chainOf,
  clusterByX,
  orthPath,
  pickFindingSide,
} from "./layout";

const measure = (text: string) => text.length * 6;

function nodeMap(result: ReturnType<typeof buildGraph>) {
  return new Map(result.nodes.map((node) => [node.id, node]));
}

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
    lines: 10,
    messagesCount: 10,
    toolUseId: null,
    skillName: null,
    teamName: null,
    events: [],
    ...overrides,
  };
}

describe("agent-tree chain layout", () => {
  it("uses assistant message offsets for compressed gaps", () => {
    const chain = chainOf(
      [
        { kind: "skill", line: 4, messageOffset: 3, name: "alpha", desc: "a", toolUseId: "s" },
        { kind: "agent", line: 12, messageOffset: 7, name: "beta", desc: "b", toolUseId: "a" },
      ],
      12,
      measure,
    );

    expect(chain.items.map((item) => item.kind)).toEqual([
      "gap",
      "skill",
      "gap",
      "agent",
      "gap",
    ]);
    expect(chain.items.filter((item) => item.kind === "gap").map((item) => item.n)).toEqual([
      3, 4, 5,
    ]);
    expect(chain.offsets).toHaveLength(2);
    expect(chain.offsets[0]).toBeGreaterThan(0);
    expect(chain.offsets[1]).toBeGreaterThan(chain.offsets[0]!);
    expect(chain.items[1]).toMatchObject({ kind: "skill", line: 4, evIdx: 0 });
    expect(chain.items[3]).toMatchObject({ kind: "agent", line: 12, evIdx: 1 });
  });

  it("keeps a single message gap when an agent has no trigger events", () => {
    const chain = chainOf([], 17, measure);
    expect(chain.items).toEqual([{ kind: "gap", n: 17, w: expect.any(Number) }]);
    expect(chain.width).toBeGreaterThanOrEqual(60);
  });

  it("scales Agent bar width from transcript line count", () => {
    const short = chainOf([], 100, measure, 10);
    const medium = chainOf([], 100, measure, 100);
    const long = chainOf([], 100, measure, 1_000);

    expect(short.width).toBeLessThan(medium.width);
    expect(medium.width).toBeLessThan(long.width);
    expect(long.width).toBeLessThanOrEqual(520);
  });
});

describe("agent-tree graph layout", () => {
  it("nests A and B under main and C under A using expansion", () => {
    const result = buildGraph(demoNestedTree, new Set(["main"]), measure);
    const nodes = nodeMap(result);

    expect(nodes.get("main")?.data.kind).toBe("root");
    expect(nodes.get("agent-a")?.data.parentAgentId).toBe("main");
    expect(nodes.get("agent-b")?.data.parentAgentId).toBe("main");
    expect(nodes.get("agent-c")?.data.parentAgentId).toBe("agent-a");
    expect(nodes.get("agent-a")?.position.y).toBeLessThan(nodes.get("agent-b")!.position.y);
    expect(nodes.get("agent-c")?.position.y).toBeGreaterThan(nodes.get("agent-a")!.position.y);
    expect(result.edges.find((edge) => edge.target === "agent-a")).toMatchObject({
      source: "main",
      sourceHandle: "h0",
      targetHandle: "in",
      type: "orth",
    });
    expect(result.edges.find((edge) => edge.target === "agent-c")).toMatchObject({
      source: "agent-a",
      sourceHandle: "h1",
    });
  });

  it("collapses more than eight siblings until the parent is expanded", () => {
    const collapsed = buildGraph(demoNestedTree, new Set(), measure);
    const collapsedNodes = nodeMap(collapsed);
    expect(collapsedNodes.has("main-group")).toBe(true);
    expect(collapsedNodes.has("agent-a")).toBe(false);
    expect(collapsed.edges.find((edge) => edge.target === "main-group")).toBeDefined();

    const expanded = buildGraph(demoNestedTree, new Set(["main"]), measure);
    expect(nodeMap(expanded).has("main-group")).toBe(false);
    expect(expanded.nodes.filter((node) => node.type === "agent")).toHaveLength(13);
  });

  it("does not group distant sibling triggers merely because their messages are adjacent", () => {
    const tree: SessionTree = {
      sessionId: "trunks",
      agents: [
        agent({
          events: [
            { kind: "agent", line: 10, messageOffset: 10, name: "A", desc: "A", toolUseId: "a" },
            { kind: "agent", line: 11, messageOffset: 11, name: "B", desc: "B", toolUseId: "b" },
            { kind: "agent", line: 70, messageOffset: 70, name: "C", desc: "C", toolUseId: "c" },
          ],
        }),
        agent({ agentId: "a", parentAgentId: "main", kind: "subagent", label: "A", toolUseId: "a" }),
        agent({ agentId: "b", parentAgentId: "main", kind: "subagent", label: "B", toolUseId: "b" }),
        agent({ agentId: "c", parentAgentId: "main", kind: "subagent", label: "C", toolUseId: "c" }),
      ],
      badCases: [],
    };
    const result = buildGraph(tree, new Set(["main"]), measure);
    const edges = new Map(result.edges.map((edge) => [edge.target, edge]));
    expect(edges.get("a")?.data?.trunkX).not.toBe(edges.get("b")?.data?.trunkX);
    expect(edges.get("b")?.data?.trunkX).not.toBe(edges.get("c")?.data?.trunkX);
    expect(result.branchSegments).toHaveLength(3);
  });

  it("groups only trigger X positions within 24 pixels", () => {
    expect(
      clusterByX([100, 120, 157], (value) => value).map((cluster) => cluster),
    ).toEqual([[100, 120], [157]]);
  });

  it("does not attach an unknown ordinary child to a workflow trigger", () => {
    const tree: SessionTree = {
      sessionId: "unknown-tool",
      agents: [
        agent({
          events: [
            {
              kind: "workflow",
              line: 4,
              messageOffset: 4,
              name: "workflow",
              desc: "workflow",
              toolUseId: "workflow-tool",
            },
          ],
        }),
        agent({
          agentId: "ordinary",
          parentAgentId: "main",
          kind: "subagent",
          agentType: "general-purpose",
          label: "ordinary",
          toolUseId: "unknown-tool",
        }),
      ],
      badCases: [],
    };

    const result = buildGraph(tree, new Set(["main"]), measure);
    const edge = result.edges.find((item) => item.target === "ordinary");

    expect(result.diagnostics.map((item) => item.code)).toContain(
      "MISSING_PARENT_EVENT",
    );
    expect(edge?.sourceHandle).not.toBe("h0");
  });

  it("expands wide trigger chains instead of placing handles outside the node", () => {
    const childEvents = Array.from({ length: 20 }, (_, index) => ({
      kind: "skill" as const,
      line: index + 1,
      messageOffset: index + 1,
      name: `long-trigger-${index}`,
      desc: `trigger-${index}`,
      toolUseId: `skill-${index}`,
    }));
    const tree: SessionTree = {
      sessionId: "wide-chain",
      agents: [
        agent({
          events: [
            {
              kind: "agent",
              line: 1,
              messageOffset: 1,
              name: "wide",
              desc: "wide",
              toolUseId: "wide-tool",
            },
          ],
        }),
        agent({
          agentId: "wide",
          parentAgentId: "main",
          kind: "subagent",
          label: "wide",
          lines: 40,
          messagesCount: 20,
          toolUseId: "wide-tool",
          events: childEvents,
        }),
      ],
      badCases: [],
    };
    const result = buildGraph(tree, new Set(["main"]), measure);
    const wide = nodeMap(result).get("wide")!;
    const lastOffset = Math.max(...wide.data.chain.offsets);

    expect(wide.data.boxW).toBeGreaterThanOrEqual(
      wide.data.chain.width + 2 * (BOX_PAD + BOX_EDGE),
    );
    expect(lastOffset + BOX_PAD + BOX_EDGE).toBeLessThanOrEqual(wide.data.boxW);
  });

  it("keeps every core-demo trigger connected to a rendered Agent", () => {
    const main = demoCoreTree.agents.find((item) => item.agentId === "main")!;
    const renderedToolIds = new Set(
      demoCoreTree.agents
        .filter((item) => item.kind !== "main")
        .map((item) => item.toolUseId)
        .filter(Boolean),
    );

    expect(
      main.events.filter((event) => event.kind === "agent" || event.kind === "workflow"),
    ).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ toolUseId: "tool-a" }),
        expect.objectContaining({ toolUseId: "tool-b" }),
      ]),
    );
    for (const event of main.events) {
      if (event.kind === "agent" || event.kind === "workflow") {
        expect(renderedToolIds.has(event.toolUseId)).toBe(true);
      }
    }
  });

  it("records the collapse branch as an obstacle for finding placement", () => {
    const collapsed = buildGraph(demoNestedTree, new Set(["agent-a"]), measure);

    expect(collapsed.edges.some((edge) => edge.target === "main-group")).toBe(true);
    expect(
      collapsed.branchSegments.some((segment) => segment.target === "main-group"),
    ).toBe(true);
  });

  it("measures Agent labels with the rendered 11px font", () => {
    const fonts: string[] = [];
    const recordingMeasure = (text: string, font: string) => {
      fonts.push(font);
      return text.length * 7;
    };

    buildGraph(demoCoreTree, new Set(["main"]), recordingMeasure);

    expect(FONT_AGENT_LABEL.startsWith("11px")).toBe(true);
    expect(fonts).toContain(FONT_AGENT_LABEL);
  });

  it("does not mutate input Agents while reconciling missing parent edges", () => {
    const input: SessionTree = {
      sessionId: "pure",
      agents: [
        agent({ events: [] }),
        agent({
          agentId: "orphan",
          parentAgentId: "missing",
          kind: "subagent",
          toolUseId: "orphan-tool",
        }),
      ],
      badCases: [],
    };
    const before = JSON.stringify(input);

    buildGraph(input, new Set(["main"]), measure);

    expect(JSON.stringify(input)).toBe(before);
  });

  it("fails closed instead of rendering duplicate Agent identities", () => {
    const duplicate: SessionTree = {
      sessionId: "duplicates",
      agents: [
        agent({ events: [] }),
        agent({ agentId: "same", parentAgentId: "main", kind: "subagent" }),
        agent({ agentId: "same", parentAgentId: "main", kind: "subagent" }),
      ],
      badCases: [],
    };
    const result = buildGraph(duplicate, new Set(["main"]), measure);

    expect(result.diagnostics.map((item) => item.code)).toContain("DUPLICATE_AGENT");
    expect(result.nodes).toEqual([]);
    expect(result.edges).toEqual([]);
  });

  it("fails closed when a tree contains multiple main Agents", () => {
    const duplicateMains: SessionTree = {
      sessionId: "duplicate-mains",
      agents: [
        agent({ events: [] }),
        agent({ agentId: "main-2", events: [] }),
      ],
      badCases: [],
    };
    const result = buildGraph(duplicateMains, new Set(), measure);

    expect(result.diagnostics.map((item) => item.code)).toContain("DUPLICATE_MAIN");
    expect(result.nodes).toEqual([]);
  });

  it("produces identical output after input permutations", () => {
    const permuted: SessionTree = {
      ...demoNestedTree,
      agents: [...demoNestedTree.agents].reverse(),
      badCases: [...demoNestedTree.badCases].reverse(),
    };
    const original = buildGraph(demoNestedTree, new Set(["main", "agent-a"]), measure);
    const shuffled = buildGraph(permuted, new Set(["agent-a", "main"]), measure);
    expect(JSON.stringify(shuffled)).toBe(JSON.stringify(original));
  });

  it("reports missing mains, cycles, and orphaned parents", () => {
    const noMain = buildGraph(
      { sessionId: "bad", agents: [agent({ kind: "subagent", agentId: "orphan" })], badCases: [] },
      new Set(),
      measure,
    );
    expect(noMain.diagnostics.map((item) => item.code)).toContain("MISSING_MAIN");

    const cycle = buildGraph(
      {
        sessionId: "cycle",
        agents: [
          agent(),
          agent({ agentId: "a", parentAgentId: "b", kind: "subagent", label: "A" }),
          agent({ agentId: "b", parentAgentId: "a", kind: "subagent", label: "B" }),
        ],
        badCases: [],
      },
      new Set(["main"]),
      measure,
    );
    expect(cycle.diagnostics.map((item) => item.code)).toContain("PARENT_CYCLE");
  });

  it("creates a deterministic parent event when a child trigger is missing", () => {
    const tree: SessionTree = {
      sessionId: "missing-event",
      agents: [
        agent({ events: [], lines: 4, messagesCount: 9 }),
        agent({
          agentId: "orphan-source",
          parentAgentId: "main",
          kind: "subagent",
          label: "missing source",
          toolUseId: "missing-tool",
        }),
      ],
      badCases: [],
    };
    const result = buildGraph(tree, new Set(["main"]), measure);
    expect(result.diagnostics.map((item) => item.code)).toContain(
      "MISSING_PARENT_EVENT",
    );
    expect(result.edges.find((edge) => edge.target === "orphan-source")).toMatchObject({
      sourceHandle: "h0",
      targetHandle: "in",
    });
    expect(result.nodes.find((node) => node.id === "main")?.data.chain.items).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ kind: "agent", line: 4, evIdx: 0 }),
      ]),
    );
  });

  it("maps self, discovery, and fallback anchors without rendering finding nodes", () => {
    const result = buildGraph(demoNestedTree, new Set(["main", "agent-a"]), measure);
    const anchors = new Map(result.anchors.map((anchor) => [anchor.badCaseId, anchor]));
    expect(anchors.get("case-self-skill")).toMatchObject({
      hostAgentId: "agent-a",
      kind: "self-skill",
      eventIndex: 0,
      side: "below",
    });
    expect(anchors.get("case-self-agent")).toMatchObject({
      hostAgentId: "agent-a",
      kind: "self-agent",
      eventIndex: 1,
    });
    expect(anchors.get("case-discovery")).toMatchObject({
      hostAgentId: "main",
      kind: "discovery",
      eventIndex: 0,
      side: "above",
    });
    expect(anchors.get("case-fallback")).toMatchObject({
      hostAgentId: "main",
      kind: "fallback",
      eventIndex: -1,
      side: "right",
    });
    expect((result.nodes as Array<{ type: string }>).some((node) => node.type === "finding")).toBe(
      false,
    );
  });

  it("picks the left side only when the right branch channel intersects the card range", () => {
    const choose = pickFindingSide(
      {
        targetId: "target",
        x: 100,
        y: 100,
        w: 200,
        visualW: 220,
        count: 2,
        branchSegments: [
          { source: "main", target: "sibling", x: 420, y1: 80, y2: 160 },
        ],
      },
    );
    expect(choose).toBe("left");
  });

  it("keeps public geometry constants stable", () => {
    expect({ AGENT_BOX_H, ROW_STEP, INDENT, MIN_STEP }).toEqual({
      AGENT_BOX_H: 80,
      ROW_STEP: 124,
      INDENT: 46,
      MIN_STEP: 38,
    });
  });
});

describe("orthogonal edge paths", () => {
  it("routes through a dedicated trunk without crossing target", () => {
    const path = orthPath({
      sourceX: 100,
      sourceY: 100,
      targetX: 300,
      targetY: 300,
      trunkX: 180,
    });
    expect(path).toContain("V 112");
    expect(path).toContain("H 180");
    expect(path).toContain("Q 180 300");
    expect(path).toContain("H 300");
  });
});
