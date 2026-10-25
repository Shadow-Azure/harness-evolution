import type { SessionAgent, SessionEvent } from "@harness/contracts";

import type {
  AgentChain,
  AgentGraphLayout,
  AgentLayoutEdge,
  AgentLayoutNode,
  BadCaseAnchorDescriptor,
  BadCaseAnchorOptions,
  BranchSegment,
  BuildGraphOptions,
  ChainItem,
  LayoutDiagnostic,
  LayoutTree,
  MeasureText,
} from "./types";

/** Gap between adjacent pill nodes. */
export const LINK_W = 10;
/** Horizontal pill padding included in deterministic width. */
export const PILL_PAD = 18;
/** Width reserved for a trigger's colored diamond. */
export const CDOT = 10;
/** Pill border contribution included in deterministic width. */
export const PILL_BORDER = 2;
/** Agent border-box horizontal padding. */
export const BOX_PAD = 10;
/** Agent border-box edge width. */
export const BOX_EDGE = 1;
/** Estimated Agent node height from the prototype. */
export const AGENT_BOX_H = 80;
/** Vertical distance between Agent rows. */
export const ROW_STEP = 124;
/** Base indentation for each child row. */
export const INDENT = 46;
/** Minimum horizontal step between sibling rows. */
export const MIN_STEP = 38;
/** Direct-child threshold before a collapse node appears. */
export const COLLAPSE_AFTER = 8;
/** Pixel threshold for grouping sibling trigger points. */
export const TRUNK_CLUSTER_W = 24;
/** Horizontal pixels contributed by one transcript line to the Agent bar. */
export const LINE_WIDTH_SCALE = 3.2;
/** Minimum proportional Agent bar width. */
export const MIN_LINE_BAR_W = 80;
/** Maximum proportional Agent bar width. */
export const MAX_LINE_BAR_W = 520;
/** Root Agent X coordinate. */
export const ROOT_X = 60;
/** Root Agent Y coordinate. */
export const ROOT_Y = 40;
/** Shared branch stroke color from the prototype. */
export const BRANCH_COLOR = "var(--graph-branch)";
/** Trigger pill font used by the injected measurer. */
export const FONT_PILL =
  '10px -apple-system, "SF Pro Text", "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif';
/** Agent node label font used by the injected measurer. */
export const FONT_AGENT_LABEL =
  '11px -apple-system, "SF Pro Text", "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif';
/** Mono font used by compressed-message pills. */
export const FONT_MONO_PILL =
  '10px "SF Mono", ui-monospace, Menlo, Consolas, monospace';

function approximateTextWidth(text: string): number {
  return [...text].reduce(
    (width, character) => width + (/[\u2e80-\uffff]/u.test(character) ? 10.8 : 6.3),
    0,
  );
}

function defaultMeasure(text: string): number {
  return approximateTextWidth(text);
}

function clipName(value: string): string {
  return value.length > 22 ? `${value.slice(0, 21)}…` : value;
}

function gapPillWidth(n: number, measure: MeasureText): number {
  return Math.round(measure(`× ${n}`, FONT_MONO_PILL) + PILL_PAD + PILL_BORDER);
}

function triggerPillWidth(text: string, measure: MeasureText): number {
  return Math.round(measure(text, FONT_PILL) + PILL_PAD + PILL_BORDER + CDOT);
}

function lineBarWidth(lines: number): number {
  return Math.max(
    MIN_LINE_BAR_W,
    Math.min(MAX_LINE_BAR_W, Math.round(Math.max(0, lines) * LINE_WIDTH_SCALE)),
  );
}

/**
 * Group adjacent values whose positions differ by at most the trunk threshold.
 * @param items Values in source order.
 * @param positionOf Position accessor for one value.
 * @returns Contiguous clusters.
 */
export function clusterByX<T>(
  items: readonly T[],
  positionOf: (item: T) => number,
): T[][] {
  const clusters: T[][] = [];
  for (const item of items) {
    const previous = clusters[clusters.length - 1];
    const previousLast = previous?.[previous.length - 1];
    if (
      previousLast !== undefined &&
      Math.abs(positionOf(item) - positionOf(previousLast)) <= TRUNK_CLUSTER_W
    ) {
      previous!.push(item);
    } else {
      clusters.push([item]);
    }
  }
  return clusters;
}

/**
 * Build the horizontal trigger chain for one Agent.
 * @param events Trigger events from the Session tree.
 * @param messagesCount Number of assistant messages in the Agent transcript.
 * @param measure Injected text-width function; defaults to deterministic approximation.
 * @param lines Transcript line count used for proportional bar width.
 * @returns Trigger/gap items, trigger-center offsets, and total width.
 */
export function chainOf(
  events: SessionEvent[],
  messagesCount: number,
  measure: MeasureText = defaultMeasure,
  lines: number = messagesCount,
): AgentChain {
  const items: ChainItem[] = [];
  const offsets: number[] = [];
  const order = events
    .map((event, originalIndex) => ({ event, originalIndex }))
    .sort(
      (left, right) =>
        left.event.messageOffset - right.event.messageOffset ||
        left.event.line - right.event.line ||
        left.originalIndex - right.originalIndex,
    );

  let x = 0;
  let previousOffset = 0;
  const push = (width: number) => {
    const center = x + width / 2;
    x += width + LINK_W;
    return center;
  };

  for (const { event, originalIndex } of order) {
    const gap = Math.max(0, event.messageOffset - previousOffset);
    if (gap > 0) {
      const width = gapPillWidth(gap, measure);
      items.push({ kind: "gap", n: gap, w: width });
      push(width);
    }

    const text =
      event.kind === "skill"
        ? event.name || "skill"
        : clipName(event.desc || event.name || event.kind);
    const width = triggerPillWidth(text, measure);
    items.push({
      kind: event.kind,
      name: text,
      evIdx: originalIndex,
      line: event.line,
      w: width,
    });
    offsets[originalIndex] = push(width);
    previousOffset = event.messageOffset;
  }

  const tail = Math.max(0, messagesCount - previousOffset);
  if (tail > 0 || items.length === 0) {
    const width = gapPillWidth(tail, measure);
    items.push({ kind: "gap", n: tail, w: width });
    push(width);
  }
  if (items.length > 0) x -= LINK_W;
  return {
    items,
    offsets,
    width: Math.max(lineBarWidth(lines), 60, Math.round(x)),
  };
}

function agentEventIndex(parent: SessionAgent, child: SessionAgent): number {
  if (child.toolUseId) {
    const index = parent.events.findIndex((event) => event.toolUseId === child.toolUseId);
    if (index >= 0) {
      return index;
    }
  }
  if (child.kind === "workflow" || child.agentType === "workflow-subagent") {
    return parent.events.findIndex((event) => event.kind === "workflow");
  }
  return -1;
}

function childSortKey(parent: SessionAgent, child: SessionAgent) {
  const eventIndex = agentEventIndex(parent, child);
  const event = parent.events[eventIndex];
  return {
    messageOffset: event?.messageOffset ?? Number.MAX_SAFE_INTEGER,
    line: event?.line ?? Number.MAX_SAFE_INTEGER,
    agentId: child.agentId,
  };
}

function hasParentCycle(agent: SessionAgent, byId: Map<string, SessionAgent>): boolean {
  const seen = new Set<string>([agent.agentId]);
  let parentId = agent.parentAgentId;
  while (parentId) {
    if (seen.has(parentId)) {
      return true;
    }
    seen.add(parentId);
    parentId = byId.get(parentId)?.parentAgentId ?? null;
  }
  return false;
}

function sortDiagnostics(diagnostics: LayoutDiagnostic[]): LayoutDiagnostic[] {
  return diagnostics.sort(
    (left, right) =>
      left.code.localeCompare(right.code) ||
      (left.agentId ?? "").localeCompare(right.agentId ?? ""),
  );
}

/**
 * Choose whether a finding card can stay right of its host.
 * @param input Host geometry, card size, and vertical branch channels.
 * @returns Preferred card side.
 */
export function pickFindingSide(input: {
  targetId: string;
  x: number;
  y: number;
  w: number;
  visualW: number;
  count: number;
  branchSegments: BranchSegment[];
}): "left" | "right" {
  const boxHeight = 22;
  const gap = 6;
  const totalHeight = input.count * boxHeight + Math.max(0, input.count - 1) * gap;
  const centerY = input.y + 28;
  const top = centerY - totalHeight / 2;
  const bottom = centerY + totalHeight / 2;
  const blocked = (x1: number, x2: number) =>
    input.branchSegments.some(
      (segment) =>
        segment.target !== input.targetId &&
        segment.source !== input.targetId &&
        segment.x > x1 &&
        segment.x < x2 &&
        segment.y2 > top &&
        segment.y1 < bottom,
    );
  const rightBlocked = blocked(input.x + input.w + 8, input.x + input.visualW + 346);
  const leftBlocked = blocked(input.x - 346, input.x - 8);
  return rightBlocked && !leftBlocked ? "left" : "right";
}

/**
 * Compute bad-case anchor descriptors without rendering problem cards.
 * @param input Layout nodes, Agents, read-only bad cases, and branch channels.
 * @returns Stable descriptors consumed by the later problem-card renderer.
 */
export function badCaseAnchors(input: BadCaseAnchorOptions): BadCaseAnchorDescriptor[] {
  const nodeById = new Map(input.nodes.map((node) => [node.id, node]));
  const agentById = new Map(input.agents.map((agent) => [agent.agentId, agent]));
  return [...input.badCases]
    .sort((left, right) => left.badCaseId.localeCompare(right.badCaseId))
    .map((badCase) => {
      const host = nodeById.get(badCase.anchor.agentId);
      const hostAgent = agentById.get(badCase.anchor.agentId);
      const eventIndex = badCase.anchor.eventIndex;
      if (!host || !hostAgent || eventIndex < 0) {
        return {
          badCaseId: badCase.badCaseId,
          hostAgentId: badCase.anchor.agentId,
          eventIndex: -1,
          kind: "fallback",
          side: "right",
          x: host ? host.position.x + host.data.visualW : ROOT_X,
          y: host ? host.position.y + 28 : ROOT_Y,
        };
      }

      const offset = host.data.chain.offsets[eventIndex] ?? 0;
      const anchorX = host.position.x + BOX_PAD + BOX_EDGE + offset;
      if (badCase.badCaseType === "discovery") {
        return {
          badCaseId: badCase.badCaseId,
          hostAgentId: badCase.anchor.agentId,
          eventIndex,
          kind: "discovery",
          side: "above",
          x: anchorX,
          y: host.position.y,
        };
      }
      if (badCase.objectType === "skill") {
        return {
          badCaseId: badCase.badCaseId,
          hostAgentId: badCase.anchor.agentId,
          eventIndex,
          kind: "self-skill",
          side: "below",
          x: anchorX,
          y: host.position.y + AGENT_BOX_H + 10,
        };
      }

      const side = pickFindingSide({
        targetId: host.id,
        x: host.position.x,
        y: host.position.y,
        w: host.data.w,
        visualW: host.data.visualW,
        count: 1,
        branchSegments: input.branchSegments,
      });
      return {
        badCaseId: badCase.badCaseId,
        hostAgentId: badCase.anchor.agentId,
        eventIndex,
        kind: "self-agent",
        side,
        x: side === "left" ? host.position.x : host.position.x + host.data.visualW,
        y: host.position.y + 28,
      };
    });
}

/**
 * Build deterministic DOM-independent Agent graph geometry.
 * @param tree Session tree with flat Agents and anchored read-only bad cases.
 * @param options Expansion set and injected text measurement.
 * @param explicitMeasure Optional third-argument text measurer for prototype-compatible calls.
 * @returns Nodes, edges, anchor descriptors, channels, and stable diagnostics.
 */
export function buildGraph(
  tree: LayoutTree,
  options: BuildGraphOptions | Iterable<string> = {},
  explicitMeasure?: MeasureText,
): AgentGraphLayout {
  const normalizedOptions: BuildGraphOptions =
    explicitMeasure
      ? { expanded: options as Iterable<string>, measureText: explicitMeasure }
      : "measureText" in options || "expanded" in options
      ? (options as BuildGraphOptions)
      : {};
  const expanded =
    normalizedOptions.expanded ??
    (Symbol.iterator in Object(options) ? (options as Iterable<string>) : []);
  const expandedIds = new Set(expanded);
  const measure = normalizedOptions.measureText ?? defaultMeasure;
  const diagnostics: LayoutDiagnostic[] = [];

  const agents = [...tree.agents]
    .sort((left, right) => left.agentId.localeCompare(right.agentId))
    .map((agent) => ({
      ...agent,
      events: agent.events.map((event) => ({ ...event })),
    }));
  const byId = new Map<string, SessionAgent>();
  for (const agent of agents) {
    if (byId.has(agent.agentId)) {
      diagnostics.push({
        code: "DUPLICATE_AGENT",
        agentId: agent.agentId,
        message: "Agent identity is duplicated",
      });
    } else {
      byId.set(agent.agentId, agent);
    }
  }
  if (diagnostics.some((item) => item.code === "DUPLICATE_AGENT")) {
    return {
      nodes: [],
      edges: [],
      anchors: [],
      diagnostics: sortDiagnostics(diagnostics),
      branchSegments: [],
    };
  }

  const mains = agents.filter((agent) => agent.kind === "main");
  if (mains.length !== 1) {
    diagnostics.push({
      code: mains.length === 0 ? "MISSING_MAIN" : "DUPLICATE_MAIN",
      agentId: null,
      message: `Expected exactly one main Agent, found ${mains.length}`,
    });
    return {
      nodes: [],
      edges: [],
      anchors: [],
      diagnostics: sortDiagnostics(diagnostics),
      branchSegments: [],
    };
  }
  const main = mains[0]!;

  const eventsById = new Map(
    agents.map((agent) => [
      agent.agentId,
      agent.events.map((event) => ({ ...event })),
    ]),
  );
  for (const agent of agents) {
    if (agent.kind === "main") {
      continue;
    }
    if (hasParentCycle(agent, byId)) {
      diagnostics.push({
        code: "PARENT_CYCLE",
        agentId: agent.agentId,
        message: "Agent parent chain contains a cycle",
      });
    }
  }

  for (const child of agents) {
    if (child.kind === "main") {
      continue;
    }
    if (!child.parentAgentId || !byId.has(child.parentAgentId)) {
      diagnostics.push({
        code: "ORPHAN_PARENT",
        agentId: child.agentId,
        message: "Missing parent Agent; falling back to main",
      });
      child.parentAgentId = main.agentId;
    }
    const parent = byId.get(child.parentAgentId!);
    if (!parent) {
      continue;
    }
    if (agentEventIndex(parent, child) >= 0) {
      continue;
    }
    const parentEvents = eventsById.get(parent.agentId)!;
    parentEvents.push({
      kind: child.kind === "workflow" ? "workflow" : "agent",
      line: Math.max(1, parent.lines),
      messageOffset: parent.messagesCount,
      name: child.label,
      desc: child.desc,
      toolUseId: child.toolUseId ?? `synthetic-${child.agentId}`,
    });
    child.toolUseId = child.toolUseId ?? `synthetic-${child.agentId}`;
    diagnostics.push({
      code: "MISSING_PARENT_EVENT",
      agentId: child.agentId,
      message: "Parent trigger event was synthesized at the end of the owner node",
    });
  }

  const effectiveById = new Map(
    agents.map((agent) => [
      agent.agentId,
      { ...agent, events: eventsById.get(agent.agentId) ?? agent.events },
    ]),
  );
  const childrenByParent = new Map<
    string,
    Array<{ agent: SessionAgent; originalIndex: number }>
  >();
  agents.forEach((agent, originalIndex) => {
    if (agent.kind === "main") {
      return;
    }
    const parentId = agent.parentAgentId ?? main.agentId;
    const list = childrenByParent.get(parentId) ?? [];
    list.push({ agent: effectiveById.get(agent.agentId) ?? agent, originalIndex });
    childrenByParent.set(parentId, list);
  });
  childrenByParent.forEach((children, parentId) => {
    const parent = effectiveById.get(parentId);
    if (!parent) {
      return;
    }
    children.sort((left, right) => {
      const leftSort = childSortKey(parent, left.agent);
      const rightSort = childSortKey(parent, right.agent);
      return (
        leftSort.messageOffset - rightSort.messageOffset ||
        leftSort.line - rightSort.line ||
        leftSort.agentId.localeCompare(rightSort.agentId)
      );
    });
  });

  const nodes: AgentLayoutNode[] = [];
  const edges: AgentLayoutEdge[] = [];
  const branchSegments: BranchSegment[] = [];
  let cursorY = ROOT_Y + 150;
  let row = 1;
  let lastX = ROOT_X;

  const mainChain = chainOf(
    effectiveById.get(main.agentId)!.events,
    main.messagesCount,
    measure,
    main.lines,
  );
  const mainLabelWidth = measure(main.label, FONT_AGENT_LABEL);
  const mainBoxW = Math.max(
    mainChain.width + 2 * (BOX_PAD + BOX_EDGE),
    mainLabelWidth + 2 * (BOX_PAD + BOX_EDGE) + 16,
  );
  nodes.push({
    id: main.agentId,
    type: "agent",
    position: { x: ROOT_X, y: ROOT_Y },
    data: {
      label: main.label,
      kind: "root",
      w: mainChain.width,
      boxW: mainBoxW,
      visualW: Math.max(mainBoxW, mainLabelWidth + 60),
      lines: main.lines,
      desc: main.desc,
      chain: mainChain,
      agentId: main.agentId,
      parentAgentId: null,
    },
  });

  const rowX = (triggerX: number) => {
    const x = Math.max(lastX + MIN_STEP, 40 + row * INDENT, triggerX + 14);
    lastX = x;
    return x;
  };
  const visited = new Set<string>([main.agentId]);

  const place = (parentNode: AgentLayoutNode, parentAgent: SessionAgent) => {
    if (visited.has(parentAgent.agentId) && parentAgent.agentId !== main.agentId) {
      return;
    }
    visited.add(parentAgent.agentId);
    const children = childrenByParent.get(parentAgent.agentId) ?? [];
    if (children.length === 0) {
      return;
    }
    const firstEventIndex = Math.max(agentEventIndex(parentAgent, children[0]!.agent), 0);
    if (children.length > COLLAPSE_AFTER && !expandedIds.has(parentAgent.agentId)) {
      const firstOffset =
        parentNode.data.chain.offsets[firstEventIndex] ?? parentNode.data.w * 0.45;
      const triggerX = parentNode.position.x + BOX_PAD + BOX_EDGE + firstOffset;
      const nodeId = `${parentAgent.agentId}-group`;
      const node: AgentLayoutNode = {
        id: nodeId,
        type: "collapse",
        position: { x: rowX(triggerX), y: cursorY },
        data: {
          label: `${children.length} 个子 agent · 点击展开`,
          kind: "collapse",
          w: 220,
          boxW: 220,
          visualW: 220,
          lines: 0,
          desc: "展开子 Agent",
          chain: { items: [], offsets: [], width: 220 },
          agentId: null,
          parentAgentId: parentAgent.agentId,
          parentForCollapse: parentAgent.agentId,
        },
      };
      nodes.push(node);
      edges.push({
        id: `e-${parentNode.id}-${nodeId}`,
        source: parentNode.id,
        target: nodeId,
        sourceHandle: `h${firstEventIndex}`,
        targetHandle: "in",
        type: "orth",
        data: { idx: 0, trunkX: triggerX },
        style: { stroke: BRANCH_COLOR, strokeWidth: 1.4 },
      });
      branchSegments.push({
        source: parentNode.id,
        target: nodeId,
        x: triggerX,
        y1: Math.min(parentNode.position.y + 39, node.position.y + 39),
        y2: Math.max(parentNode.position.y + 39, node.position.y + 39),
      });
      cursorY += 96;
      row += 1;
      return;
    }

    const info = children.map(({ agent }, index) => {
      const eventIndex = agentEventIndex(parentAgent, agent);
      const sourceEventIndex = Math.max(eventIndex, 0);
      const sourceEvent = parentAgent.events[sourceEventIndex];
      const offset =
        parentNode.data.chain.offsets[sourceEventIndex] ?? parentNode.data.w * 0.45;
      return {
        agent,
        index,
        eventIndex,
        sourceEventIndex,
        messageOffset: sourceEvent?.messageOffset ?? parentAgent.messagesCount,
        triggerX: parentNode.position.x + BOX_PAD + BOX_EDGE + offset,
      };
    });

    const clusters = clusterByX(info, (item) => item.triggerX);
    const trunkOf = new Map<string, number>();
    clusters.forEach((cluster) => {
      const first = cluster[0]!;
      const trunkX =
        parentNode.data.chain.offsets[first.sourceEventIndex] != null
          ? parentNode.position.x +
            BOX_PAD +
            BOX_EDGE +
            parentNode.data.chain.offsets[first.sourceEventIndex]!
          : first.triggerX;
      cluster.forEach((item) => trunkOf.set(item.agent.agentId, trunkX));
    });

    info.forEach((item) => {
      if (hasParentCycle(item.agent, byId)) {
        return;
      }
      const nodeY = cursorY;
      const nodeX = rowX(item.triggerX);
      const childEvents =
        item.agent.kind === "workflow" && item.agent.events.length === 0
          ? [
              {
                kind: "workflow" as const,
                name: "workflow run",
                desc: "workflow run",
                line: Math.max(1, Math.round(item.agent.lines / 2)),
                messageOffset: Math.round(item.agent.messagesCount / 2),
                toolUseId: null,
              },
            ]
          : item.agent.events;
      const chain = chainOf(
        childEvents,
        item.agent.messagesCount,
        measure,
        item.agent.lines,
      );
      const labelWidth = measure(item.agent.label, FONT_AGENT_LABEL);
      const boxW = Math.max(
        chain.width + 2 * (BOX_PAD + BOX_EDGE),
        labelWidth + 2 * (BOX_PAD + BOX_EDGE) + 16,
      );
      const visualW = Math.max(boxW, labelWidth + 60);
      const node: AgentLayoutNode = {
        id: item.agent.agentId,
        type: "agent",
        position: { x: nodeX, y: nodeY },
        data: {
          label: item.agent.label,
          kind: item.agent.kind === "workflow" ? "wf" : "sub",
          w: chain.width,
          boxW,
          visualW,
          lines: item.agent.lines,
          desc: item.agent.desc,
          chain,
          agentId: item.agent.agentId,
          parentAgentId: item.agent.parentAgentId,
        },
      };
      nodes.push(node);
      const trunkX = trunkOf.get(item.agent.agentId) ?? item.triggerX;
      edges.push({
        id: `e-${parentNode.id}-${item.agent.agentId}`,
        source: parentNode.id,
        target: item.agent.agentId,
        sourceHandle: `h${item.sourceEventIndex}`,
        targetHandle: "in",
        type: "orth",
        data: { idx: item.index, trunkX },
        style: { stroke: BRANCH_COLOR, strokeWidth: 1.4 },
      });
      branchSegments.push({
        source: parentNode.id,
        target: item.agent.agentId,
        x: trunkX,
        y1: Math.min(parentNode.position.y + 39, nodeY + 39),
        y2: Math.max(parentNode.position.y + 39, nodeY + 39),
      });
      cursorY += ROW_STEP;
      row += 1;
      place(node, effectiveById.get(item.agent.agentId) ?? item.agent);
    });
  };

  place(nodes[0]!, effectiveById.get(main.agentId)!);

  const anchors = badCaseAnchors({
    nodes,
    agents,
    badCases: tree.badCases,
    branchSegments,
  });
  for (const badCase of tree.badCases) {
    if (!nodes.some((node) => node.id === badCase.anchor.agentId)) {
      diagnostics.push({
        code: "MISSING_ANCHOR_AGENT",
        agentId: badCase.anchor.agentId,
        message: "Bad-case anchor Agent is not present in the assembled graph",
      });
    }
  }

  return {
    nodes,
    edges,
    anchors,
    diagnostics: sortDiagnostics(diagnostics),
    branchSegments,
  };
}

/**
 * Build a rounded orthogonal branch path.
 * @param input Source/target coordinates and optional shared trunk X.
 * @returns SVG path data.
 */
export function orthPath(input: {
  sourceX: number;
  sourceY: number;
  targetX: number;
  targetY: number;
  trunkX?: number;
}): string {
  const jogY = input.sourceY + 12;
  const trunk = input.trunkX ?? Math.min(input.sourceX + 8, Math.max(0, input.targetX - 8));
  const radius = Math.min(
    8,
    Math.max(0, input.targetX - trunk) / 2,
    Math.max(0, input.targetY - jogY) / 2,
  );
  return [
    `M ${input.sourceX} ${input.sourceY}`,
    `V ${jogY}`,
    `H ${trunk}`,
    `V ${input.targetY - radius}`,
    `Q ${trunk} ${input.targetY} ${trunk + radius} ${input.targetY}`,
    `H ${input.targetX}`,
  ].join(" ");
}
