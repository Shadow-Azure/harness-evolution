import type { BadCase, SessionAgent, SessionEvent } from "@harness/contracts";

import { shortBadCaseId } from "../../utils/badCaseId";

import type {
  AgentChain,
  AgentGraphLayout,
  AgentLayoutEdge,
  AgentLayoutNode,
  BadCaseLayoutEdge,
  BadCaseLayoutNode,
  BadCaseAnchorDescriptor,
  BadCaseAnchorOptions,
  BranchSegment,
  BuildGraphOptions,
  ChainItem,
  LayoutDiagnostic,
  LayoutTree,
  MeasureText,
  TriggerConnection,
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
/** Trigger-pill top anchor used by upward edges. */
export const TRIGGER_HANDLE_TOP = 31;
/** Trigger-pill bottom anchor used by downward edges. */
export const TRIGGER_HANDLE_BOTTOM = 53;
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
/** Minimum problem-card width in the prototype graph. */
export const BADCASE_CARD_MIN_W = 150;
/** Maximum problem-card width in the prototype graph. */
export const BADCASE_CARD_MAX_W = 400;
/** Problem-card height in the prototype graph. */
export const BADCASE_CARD_H = 30;
/** Vertical gap between stacked problem cards. */
export const BADCASE_CARD_GAP = 6;
/** Root Agent X coordinate. */
export const ROOT_X = 60;
/** Root Agent Y coordinate. */
export const ROOT_Y = 40;
/** Shared branch stroke color from the prototype. */
export const BRANCH_COLOR = "var(--graph-branch)";
/** Problem-card connector color from the prototype. */
export const BADCASE_COLOR = "var(--red)";
/** Trigger pill font used by the injected measurer. */
export const FONT_PILL =
  '10px -apple-system, "SF Pro Text", "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif';
/** Agent node label font used by the injected measurer. */
export const FONT_AGENT_LABEL =
  '11px -apple-system, "SF Pro Text", "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif';
/** Problem-card label font used by the injected measurer. */
export const FONT_BADCASE =
  '10.5px -apple-system, "SF Pro Text", "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif';
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
  const totalHeight =
    input.count * BADCASE_CARD_H +
    Math.max(0, input.count - 1) * BADCASE_CARD_GAP;
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
  const cardReach = BADCASE_CARD_MAX_W + 46;
  const rightBlocked = blocked(
    input.x + input.w + 8,
    input.x + input.visualW + cardReach,
  );
  const leftBlocked = blocked(input.x - cardReach, input.x - 8);
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
  const cases = [...input.badCases].sort((left, right) =>
    left.badCaseId.localeCompare(right.badCaseId),
  );
  const selfAgentCounts = new Map<string, number>();
  for (const badCase of cases) {
    const host = nodeById.get(badCase.anchor.agentId);
    const hostAgent = agentById.get(badCase.anchor.agentId);
    const eventIndex = badCase.anchor.eventIndex;
    if (
      !host ||
      !hostAgent ||
      eventIndex < 0 ||
      !hostAgent.events[eventIndex] ||
      host.data.chain.offsets[eventIndex] === undefined ||
      badCase.badCaseType === "discovery" ||
      badCase.objectType === "skill"
    ) {
      continue;
    }
    const key = badCase.anchor.agentId;
    selfAgentCounts.set(key, (selfAgentCounts.get(key) ?? 0) + 1);
  }

  return cases
    .map((badCase) => {
      const host = nodeById.get(badCase.anchor.agentId);
      const hostAgent = agentById.get(badCase.anchor.agentId);
      const eventIndex = badCase.anchor.eventIndex;
      if (!host && hostAgent) {
        return {
          badCaseId: badCase.badCaseId,
          hostAgentId: badCase.anchor.agentId,
          eventIndex: -1,
          kind: "hidden",
          side: "right",
          x: ROOT_X,
          y: ROOT_Y,
        };
      }
      if (
        !host ||
        !hostAgent ||
        eventIndex < 0 ||
        !hostAgent.events[eventIndex] ||
        host.data.chain.offsets[eventIndex] === undefined
      ) {
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
        count:
          selfAgentCounts.get(badCase.anchor.agentId) ?? 1,
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

function badCaseEdgeType(
  anchor: BadCaseAnchorDescriptor,
): BadCaseLayoutEdge["type"] {
  if (anchor.kind === "self-skill") {
    return "trigger";
  }
  if (anchor.kind === "discovery") {
    return "discovery";
  }
  return "badcase";
}

function badCaseHandles(
  anchor: BadCaseAnchorDescriptor,
): Pick<BadCaseLayoutEdge, "sourceHandle" | "targetHandle"> {
  if (anchor.kind === "self-agent" || anchor.kind === "fallback") {
    return {
      sourceHandle:
        anchor.side === "left" ? "finding-left" : "finding-right",
      targetHandle: anchor.side === "left" ? "card-right" : "card-left",
    };
  }
  if (anchor.kind === "discovery") {
    return {
      sourceHandle: `rep${anchor.eventIndex}`,
      targetHandle: "card-bottom",
    };
  }
  return {
    sourceHandle: `h${anchor.eventIndex}`,
    targetHandle: "card-top",
  };
}

/**
 * Measure a problem card's prototype-clamped single-line width.
 * @param shortId Display-safe problem identifier.
 * @param reason Human-readable problem summary.
 * @param measure Injected text measurement function.
 * @returns Rounded border-box width.
 */
export function badCaseCardWidth(
  shortId: string,
  reason: string,
  measure: MeasureText = defaultMeasure,
): number {
  return Math.round(
    Math.max(
      BADCASE_CARD_MIN_W,
      Math.min(
        BADCASE_CARD_MAX_W,
        measure(`${shortId} ${reason}`, FONT_BADCASE) + 26,
      ),
    ),
  );
}

/**
 * Place problem cards around their backend-provided anchors.
 * @param anchors Stable anchor descriptors.
 * @param treeCases Minimal bad cases carried by the Session tree.
 * @param details Full problem records used for problem presentation.
 * @param measure Injected text measurement function.
 * @returns Stable card nodes and their semantic connector edges.
 */
export function buildBadCaseOverlay(
  anchors: BadCaseAnchorDescriptor[],
  treeCases: BadCaseAnchorOptions["badCases"],
  details: readonly BadCase[] = [],
  measure: MeasureText = defaultMeasure,
): {
  badCaseNodes: BadCaseLayoutNode[];
  badCaseEdges: BadCaseLayoutEdge[];
} {
  const caseById = new Map(treeCases.map((item) => [item.badCaseId, item]));
  const detailById = new Map(details.map((item) => [item.badCaseId, item]));
  const sortedAnchors = [...anchors]
    .filter((anchor) => anchor.kind !== "hidden")
    .sort((left, right) => left.badCaseId.localeCompare(right.badCaseId));
  const nodesById = new Map<string, BadCaseLayoutNode>();
  const placed: Array<{
    id: string;
    x: number;
    y: number;
    width: number;
  }> = [];
  const stackedSourceById = new Map<
    string,
    {
      source: string;
      sourceHandle: string;
      targetHandle: string;
    }
  >();

  const overlaps = (
    left: { x: number; y: number; width: number },
    right: { x: number; y: number; width: number },
  ) =>
    !(
      left.x + left.width + BADCASE_CARD_GAP <= right.x ||
      right.x + right.width + BADCASE_CARD_GAP <= left.x ||
      left.y + BADCASE_CARD_H + BADCASE_CARD_GAP <= right.y ||
      right.y + BADCASE_CARD_H + BADCASE_CARD_GAP <= left.y
    );

  const addNode = (
    anchor: BadCaseAnchorDescriptor,
    x: number,
    y: number,
  ): BadCaseLayoutNode | null => {
    const item = caseById.get(anchor.badCaseId);
    const detail = detailById.get(anchor.badCaseId);
    if (!item) return null;
    const shortId = shortBadCaseId(anchor.badCaseId);
    const reason = detail?.reason ?? item.reason;
    const width = badCaseCardWidth(shortId, reason, measure);
    const node: BadCaseLayoutNode = {
      id: `badcase:${anchor.badCaseId}`,
      type: "badcase",
      position: { x, y },
      data: {
        badCaseId: anchor.badCaseId,
        shortId,
        reason,
        width,
        degraded: detail?.degraded ?? false,
      },
    };
    nodesById.set(node.id, node);
    placed.push({ id: node.id, x, y, width });
    return node;
  };

  const sideGroups = new Map<string, BadCaseAnchorDescriptor[]>();
  const verticalGroups = new Map<string, BadCaseAnchorDescriptor[]>();
  for (const anchor of sortedAnchors) {
    if (anchor.side !== "left" && anchor.side !== "right") {
      const key = `${anchor.hostAgentId}|${anchor.eventIndex}|${anchor.side}`;
      const group = verticalGroups.get(key) ?? [];
      group.push(anchor);
      verticalGroups.set(key, group);
      continue;
    }
    const key = `${anchor.hostAgentId}|${anchor.side}`;
    const group = sideGroups.get(key) ?? [];
    group.push(anchor);
    sideGroups.set(key, group);
  }

  for (const group of sideGroups.values()) {
    group.forEach((anchor, index) => {
      const item = caseById.get(anchor.badCaseId);
      if (!item) return;
      const detail = detailById.get(anchor.badCaseId);
      const width = badCaseCardWidth(
        shortBadCaseId(anchor.badCaseId),
        detail?.reason ?? item.reason,
        measure,
      );
      const y =
        anchor.y -
        BADCASE_CARD_H / 2 +
        (index - (group.length - 1) / 2) *
          (BADCASE_CARD_H + BADCASE_CARD_GAP);
      const x =
        anchor.side === "left"
          ? anchor.x - width - 46
          : anchor.x + 46;
      addNode(anchor, x, y);
    });
  }

  for (const group of verticalGroups.values()) {
    const direction = group[0]!.side === "above" ? -1 : 1;
    let previous: BadCaseLayoutNode | null = null;
    group.forEach((anchor, index) => {
      const item = caseById.get(anchor.badCaseId);
      if (!item) return;
      const detail = detailById.get(anchor.badCaseId);
      const width = badCaseCardWidth(
        shortBadCaseId(anchor.badCaseId),
        detail?.reason ?? item.reason,
        measure,
      );
      const x = Math.max(8, anchor.x - width / 2);
      const baseY =
        anchor.side === "above"
          ? anchor.y - 8 - BADCASE_CARD_H
          : anchor.y + 8;
      let y = baseY + direction * index * (BADCASE_CARD_H + BADCASE_CARD_GAP);
      while (
        placed.some((candidate) =>
          overlaps(
            { x, y, width },
            { x: candidate.x, y: candidate.y, width: candidate.width },
          ),
        )
      ) {
        y += direction * (BADCASE_CARD_H + BADCASE_CARD_GAP);
      }
      const node = addNode(anchor, x, y);
      if (!node) return;
      if (previous) {
        stackedSourceById.set(anchor.badCaseId, {
          source: previous.id,
          sourceHandle:
            anchor.side === "above" ? "card-stack-top" : "card-stack-bottom",
          targetHandle:
            anchor.side === "above" ? "card-bottom" : "card-top",
        });
      }
      previous = node;
    });
  }

  const badCaseNodes = [...nodesById.values()].sort((left, right) =>
    left.data.badCaseId.localeCompare(right.data.badCaseId),
  );
  const badCaseEdges = sortedAnchors
    .filter((anchor) => nodesById.has(`badcase:${anchor.badCaseId}`))
    .map((anchor): BadCaseLayoutEdge => {
      const stacked = stackedSourceById.get(anchor.badCaseId);
      return {
        id: `e-${anchor.hostAgentId}-${anchor.eventIndex}-${anchor.badCaseId}`,
        source: stacked?.source ?? anchor.hostAgentId,
        target: `badcase:${anchor.badCaseId}`,
        ...(stacked
          ? {
              sourceHandle: stacked.sourceHandle,
              targetHandle: stacked.targetHandle,
            }
          : badCaseHandles(anchor)),
        type: badCaseEdgeType(anchor),
        data: {
          badCaseId: anchor.badCaseId,
          side: anchor.side,
        },
        style: {
          stroke: BADCASE_COLOR,
          strokeWidth: 1.2,
          strokeDasharray: "4 3",
        },
      };
    });

  return { badCaseNodes, badCaseEdges };
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
      badCaseNodes: [],
      badCaseEdges: [],
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
      badCaseNodes: [],
      badCaseEdges: [],
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
    if (!agents.some((agent) => agent.agentId === badCase.anchor.agentId)) {
      diagnostics.push({
        code: "MISSING_ANCHOR_AGENT",
        agentId: badCase.anchor.agentId,
        message: "Bad-case anchor Agent is not present in the assembled graph",
      });
    }
  }
  const overlay = buildBadCaseOverlay(
    anchors,
    tree.badCases,
    normalizedOptions.problemDetails,
    measure,
  );
  const triggerConnectionsByAgent = new Map<
    string,
    Record<number, TriggerConnection>
  >();
  for (const edge of [...edges, ...overlay.badCaseEdges]) {
    if (!nodes.some((node) => node.id === edge.source)) {
      continue;
    }
    const below = /^h(\d+)$/.exec(edge.sourceHandle);
    const above = /^rep(\d+)$/.exec(edge.sourceHandle);
    const match = below ?? above;
    if (!match) {
      continue;
    }
    const eventIndex = Number(match[1]);
    const connections =
      triggerConnectionsByAgent.get(edge.source) ?? {};
    const current = connections[eventIndex] ?? {};
    connections[eventIndex] = {
      ...current,
      ...(below ? { below: true } : { above: true }),
    };
    triggerConnectionsByAgent.set(edge.source, connections);
  }
  for (const node of nodes) {
    const triggerConnections = triggerConnectionsByAgent.get(node.id);
    if (triggerConnections) {
      node.data.triggerConnections = triggerConnections;
    }
  }
  const renderedNodeIds = new Set([
    ...nodes.map((node) => node.id),
    ...overlay.badCaseNodes.map((node) => node.id),
  ]);

  return {
    nodes,
    edges,
    badCaseNodes: overlay.badCaseNodes,
    badCaseEdges: overlay.badCaseEdges.filter((edge) =>
      renderedNodeIds.has(edge.source),
    ),
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

/**
 * Build the side-to-side connector used by self-Agent problem cards.
 * @param input Source and target coordinates.
 * @returns SVG path data.
 */
export function badCasePath(input: {
  sourceX: number;
  sourceY: number;
  targetX: number;
  targetY: number;
}): string {
  const dy = input.targetY - input.sourceY;
  if (dy === 0) {
    return `M ${input.sourceX} ${input.sourceY} H ${input.targetX}`;
  }
  const direction = Math.sign(input.targetX - input.sourceX) || 1;
  const horizontalDistance = Math.abs(input.targetX - input.sourceX);
  const trunk =
    input.sourceX +
    direction * Math.min(24, horizontalDistance / 2);
  const verticalDirection = Math.sign(dy);
  const radius = Math.min(
    7,
    Math.abs(dy) / 2,
    Math.abs(trunk - input.sourceX),
    Math.abs(input.targetX - trunk),
  );
  return [
    `M ${input.sourceX} ${input.sourceY}`,
    `H ${trunk - direction * radius}`,
    `Q ${trunk} ${input.sourceY} ${trunk} ${input.sourceY + verticalDirection * radius}`,
    `V ${input.targetY - verticalDirection * radius}`,
    `Q ${trunk} ${input.targetY} ${trunk + direction * radius} ${input.targetY}`,
    `H ${input.targetX}`,
  ].join(" ");
}

/**
 * Build a horizontal-then-vertical trigger connector for a skill card.
 * @param input Source and target coordinates.
 * @returns SVG path data.
 */
export function triggerPath(input: {
  sourceX: number;
  sourceY: number;
  targetX: number;
  targetY: number;
}): string {
  const directionX = Math.sign(input.targetX - input.sourceX) || 1;
  const directionY = Math.sign(input.targetY - input.sourceY) || -1;
  const radius = Math.min(
    6,
    Math.abs(input.targetX - input.sourceX) / 2,
    Math.abs(input.targetY - input.sourceY) / 2,
  );
  return [
    `M ${input.sourceX} ${input.sourceY}`,
    `H ${input.targetX - directionX * radius}`,
    `Q ${input.targetX} ${input.sourceY} ${input.targetX} ${input.sourceY + directionY * radius}`,
    `V ${input.targetY}`,
  ].join(" ");
}

/**
 * Build the discovery connector from a top trigger handle toward its card.
 * @param input Source and target coordinates.
 * @returns SVG path data.
 */
export function discoveryPath(input: {
  sourceX: number;
  sourceY: number;
  targetX: number;
  targetY: number;
}): string {
  const radius = Math.min(7, Math.abs(input.targetY - input.sourceY) / 2);
  return [
    `M ${input.sourceX} ${input.sourceY}`,
    `V ${input.targetY + radius}`,
    `Q ${input.sourceX} ${input.targetY} ${input.sourceX + radius} ${input.targetY}`,
    `H ${input.targetX}`,
  ].join(" ");
}
