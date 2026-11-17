import type { SessionAgent, SessionBadCase, SessionEvent } from "@harness/contracts";

import type {
  BadCaseMarker,
  ConcurrencyBand,
  Lane,
  LaneBar,
  LaneBarKind,
  LaneDiagnostic,
  LaneModel,
  LaneRailLabel,
  LaneSpawnGroup,
  LayoutTree,
} from "../types";
import {
  LANE_BAR_H,
  LANE_BAR_TOP,
  LANE_MAIN_BAR_TOP,
  LANE_MAIN_ROW_H,
  LANE_MAIN_TRACK_H,
  LANE_AXIS_H,
  LANE_ROW_H,
  LANE_TOP,
  LANE_TRACK_H,
} from "../types";

const MAX_SUB_WIDTH = 42;
const MIN_BAR_WIDTH = 0.45;
const MAX_AXIS = 100;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function emptyModel(diagnostics: LaneDiagnostic[]): LaneModel {
  return {
    lanes: [],
    width: 1100,
    height: LANE_TOP + LANE_MAIN_ROW_H,
    mainLines: 1,
    caseMarkers: [],
    concurrencyBands: [],
    spawnGroups: [],
    diagnostics,
  };
}

function shortLabel(value: string, max = 24): string {
  const text = value.trim() || "step";
  if (text.length <= max) {
    return text;
  }
  const tail = text.includes(":") ? text.slice(text.lastIndexOf(":") + 1) : text;
  return tail.length <= max ? tail : `${text.slice(0, max - 1)}…`;
}

function eventLabel(event: SessionEvent): string {
  const raw = event.desc || event.name || event.kind || "step";
  return shortLabel(raw);
}

function emptyDiagnostics(): LaneDiagnostic[] {
  return [];
}

/**
 * Build the lane DAG model from the flat Session tree.
 *
 * One lane is one agent invocation, identified by an `A1/A1.1` path. Bars are
 * log-line intervals on the 0–100 axis: a trigger event occupies its line, a
 * no-trigger gap occupies every line between triggers. Same-lane bars never
 * overlap; different lanes sharing horizontal space express concurrency.
 *
 * @param tree Session tree with agents and anchored bad cases.
 * @param selectedCaseId Currently selected bad case, used only for highlighting.
 * @returns Deterministic lane model consumed by `LaneDag.vue`.
 */
export function buildLaneModel(
  tree: LayoutTree,
  selectedCaseId?: string | null,
): LaneModel {
  const diagnostics = emptyDiagnostics();
  const agents = tree.agents.map((agent) => ({ ...agent }));
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
    return emptyModel(diagnostics);
  }

  const mains = agents.filter((agent) => agent.kind === "main");
  if (mains.length !== 1) {
    diagnostics.push({
      code: mains.length === 0 ? "MISSING_MAIN" : "DUPLICATE_MAIN",
      agentId: null,
      message: `Expected exactly one main Agent, found ${mains.length}`,
    });
    return emptyModel(diagnostics);
  }
  const main = mains[0]!;
  const mainLines = Math.max(1, main.lines);

  for (const agent of agents) {
    if (agent.kind === "main") {
      continue;
    }
    if (hasParentCycle(agent, byId)) {
      diagnostics.push({
        code: "PARENT_CYCLE",
        agentId: agent.agentId,
        message: "Agent parent chain contains a cycle; falling back to main",
      });
      agent.parentAgentId = main.agentId;
    }
  }

  const childrenByParent = new Map<string, SessionAgent[]>();
  for (const agent of agents) {
    if (agent.kind === "main") {
      continue;
    }
    let parentId = agent.parentAgentId;
    if (!parentId || !byId.has(parentId)) {
      diagnostics.push({
        code: "ORPHAN_PARENT",
        agentId: agent.agentId,
        message: "Missing parent Agent; falling back to main",
      });
      parentId = main.agentId;
    }
    const list = childrenByParent.get(parentId) ?? [];
    list.push(agent);
    childrenByParent.set(parentId, list);
  }

  const orderedChildren = new Map<string, SessionAgent[]>();
  childrenByParent.forEach((children, parentId) => {
    const parent = byId.get(parentId);
    if (!parent) {
      return;
    }
    children.sort((left, right) => {
      const leftLine = triggerLineOf(parent, left);
      const rightLine = triggerLineOf(parent, right);
      return (
        leftLine - rightLine ||
        left.label.localeCompare(right.label) ||
        left.agentId.localeCompare(right.agentId)
      );
    });
    orderedChildren.set(parentId, children);
  });

  const mainBars = buildMainBars(main, mainLines);
  const laneById = new Map<string, Lane>();
  const lanes: Lane[] = [];

  const mainLane: Lane = {
    id: main.agentId,
    path: "A1",
    depth: 0,
    label: main.label || "main",
    full: `${main.label || "main"} · ${mainLines} 行（逻辑序）`,
    top: LANE_TOP,
    start: 0,
    end: MAX_AXIS,
    lines: mainLines,
    trigger: 0,
    parentId: null,
    parentBarId: null,
    kind: "main",
    state: "",
    bars: mainBars,
    events: main.events,
    cases: [],
    railLabels: buildRailLabels(mainBars),
    barTop: LANE_MAIN_BAR_TOP,
    trackH: LANE_MAIN_TRACK_H,
    rowH: LANE_MAIN_ROW_H,
  };
  lanes.push(mainLane);
  laneById.set(mainLane.id, mainLane);

  let maxSubLines = 1;
  for (const agent of agents) {
    if (agent.kind !== "main" && agent.lines > 0) {
      maxSubLines = Math.max(maxSubLines, agent.lines);
    }
  }
  const subLineWidth = MAX_SUB_WIDTH / maxSubLines;

  const visited = new Set<string>([main.agentId]);
  const buildChildren = (parentLane: Lane, parentAgent: SessionAgent, depth: number) => {
    const children = orderedChildren.get(parentAgent.agentId) ?? [];
    const mainParent = parentLane.depth === 0;
    const bucketSize = new Map<string, number>();
    for (const child of children) {
      if (!mainParent) {
        break;
      }
      const triggerLine = triggerLineOf(parentAgent, child);
      const bar = mainBarAt(mainBars, triggerLine);
      const key = bar?.id ?? `t${triggerLine.toFixed(2)}`;
      bucketSize.set(key, (bucketSize.get(key) ?? 0) + 1);
    }
    const bucketIndex = new Map<string, number>();
    const ordered: Array<{ child: SessionAgent; start: number; parentBarId: string | null }> = [];

    children.forEach((child, childIndex) => {
      if (visited.has(child.agentId)) {
        diagnostics.push({
          code: "PARENT_CYCLE",
          agentId: child.agentId,
          message: "Agent parent chain contains a cycle",
        });
        return;
      }
      visited.add(child.agentId);
      const triggerLine = triggerLineOf(parentAgent, child);
      let start: number;
      let parentBarId: string | null = null;
      if (mainParent) {
        const parentBar = mainBarAt(mainBars, triggerLine);
        parentBarId = parentBar?.id ?? null;
        const key = parentBar?.id ?? `t${triggerLine.toFixed(2)}`;
        const position = bucketIndex.get(key) ?? 0;
        bucketIndex.set(key, position + 1);
        const total = bucketSize.get(key) ?? 1;
        const fraction = total <= 1 ? 0.5 : 0.2 + 0.6 * (position / (total - 1));
        const barWidth = parentBar ? parentBar.end - parentBar.start : MAX_AXIS;
        const barLeft = parentBar ? parentBar.start : 0;
        start = clamp(barLeft + barWidth * fraction, 0.4, MAX_AXIS - 2.4);
      } else {
        const parentBar = mainBarAt(parentLane.bars, triggerLine);
        parentBarId = parentBar?.id ?? null;
        const hasEvent = Boolean(
          child.toolUseId &&
            parentAgent.events.some((event) => event.toolUseId === child.toolUseId),
        );
        const fraction = hasEvent && parentAgent.lines > 0
          ? clamp(triggerLine / parentAgent.lines, 0.08, 0.92)
          : 0.5;
        const base = parentLane.start + (parentLane.end - parentLane.start) * fraction;
        const offset = (childIndex - (children.length - 1) / 2) * 1.2;
        start = clamp(
          base + offset,
          parentLane.start + 0.4,
          Math.max(parentLane.start + 0.4, parentLane.end - 2.4),
        );
      }
      ordered.push({ child, start, parentBarId });
    });

    ordered.forEach(({ child, start, parentBarId }, index) => {
      const path = `${parentLane.path}.${index + 1}`;
      const known = child.lines > 0;
      const width = known
        ? Math.max(2.2, child.lines * subLineWidth)
        : Math.max(2.2, parentLane.end - start);
      const desired = start + width;
      const end = Math.min(MAX_AXIS, desired);
      const cont = desired > MAX_AXIS + 0.001;
      const laneKind = depth === 1 ? "sub" : "sub2";
      const lane: Lane = {
        id: child.agentId,
        path,
        depth,
        label: child.desc || child.label || child.agentType || "agent",
        full: [
          child.label || child.agentId,
          known ? `${child.lines} 行` : "行数 unknown",
          `路径 ${path}`,
          "子 lane 长度按日志行数线性缩放，不是真实耗时",
        ].join(" · "),
        top: 0,
        start,
        end,
        lines: child.lines,
        trigger: start,
        parentId: parentLane.id,
        parentBarId,
        kind: child.kind,
        state: known ? "concurrent" : "unknown",
        bars: buildSubBars(child, laneKind, start, end, cont),
        events: child.events,
        cases: [],
        railLabels: [],
        barTop: LANE_BAR_TOP,
        trackH: LANE_TRACK_H,
        rowH: LANE_ROW_H,
      };
      lanes.push(lane);
      laneById.set(lane.id, lane);
      buildChildren(lane, child, depth + 1);
    });
  };

  buildChildren(mainLane, main, 1);

  lanes.forEach((lane, index) => {
    lane.top = index === 0
      ? LANE_TOP
      : LANE_TOP + LANE_MAIN_ROW_H + (index - 1) * LANE_ROW_H;
  });

  reconcileLanes(lanes, laneById, main.agentId);

  const caseMarkers = buildBadCaseMarkers(
    tree.badCases,
    byId,
    main,
    mainBars,
    mainLines,
    selectedCaseId ?? null,
  );
  assignCasesToLanes(caseMarkers, tree.badCases, laneById, mainLane);

  const spawnGroups = buildSpawnGroups(lanes, laneById);
  const concurrencyBands = buildConcurrencyBands(lanes);
  const height = LANE_TOP + LANE_MAIN_ROW_H + Math.max(0, lanes.length - 1) * LANE_ROW_H;
  const width = Math.max(1100, 980 + Math.max(0, mainBars.length - 6) * 80);

  return {
    lanes,
    width,
    height,
    mainLines,
    caseMarkers,
    concurrencyBands,
    spawnGroups,
    diagnostics,
  };
}

function hasParentCycle(
  agent: SessionAgent,
  byId: Map<string, SessionAgent>,
): boolean {
  const seen = new Set<string>([agent.agentId]);
  let parent = agent.parentAgentId;
  while (parent && byId.has(parent)) {
    if (seen.has(parent)) {
      return true;
    }
    seen.add(parent);
    parent = byId.get(parent)?.parentAgentId ?? null;
  }
  return false;
}

function triggerLineOf(parent: SessionAgent, child: SessionAgent): number {
  if (child.toolUseId) {
    const event = parent.events.find((item) => item.toolUseId === child.toolUseId);
    if (event) {
      return Math.max(1, event.line);
    }
  }
  return Math.max(1, parent.lines || 1);
}

function eventLabelOf(event: SessionEvent): string {
  return eventLabel(event);
}

function groupKind(members: SessionEvent[]): LaneBarKind {
  return members.every((event) => event.kind === "skill") ? "skill" : "main";
}

function buildMainBars(main: SessionAgent, mainLines: number): LaneBar[] {
  const events = [...main.events]
    .filter((event) => Number.isFinite(event.line))
    .sort((left, right) => left.line - right.line || left.messageOffset - right.messageOffset);
  const bars: LaneBar[] = [];
  let cursor = 1;
  let lastWasGap = true;
  let lastBar: LaneBar | null = null;
  let lastMembers: SessionEvent[] = [];

  const pushGap = (lo: number, hi: number) => {
    if (hi < lo) {
      return;
    }
    const span = hi - lo + 1;
    const bar: LaneBar = {
      id: `main-gap-${bars.length}`,
      laneId: main.agentId,
      label: `×${span}`,
      kind: "gap",
      start: ((lo - 1) / mainLines) * MAX_AXIS,
      end: (hi / mainLines) * MAX_AXIS,
      lo,
      hi,
      span,
      rail: false,
      title: `无触发区间 · ${span} 行日志（逻辑序，无真实时间戳）`,
    };
    bars.push(bar);
    lastWasGap = true;
    lastBar = null;
    lastMembers = [];
    cursor = hi + 1;
  };

  for (const event of events) {
    const line = clamp(event.line, 1, mainLines);
    if (line > cursor) {
      pushGap(cursor, line - 1);
    }
    if (!lastWasGap && lastBar && lastBar.kind !== "gap" && line <= (lastBar.hi ?? 0) + 1) {
      lastMembers.push(event);
      const hi = Math.max(lastBar.hi ?? line, line);
      lastBar.hi = hi;
      lastBar.span = hi - (lastBar.lo ?? line) + 1;
      lastBar.end = (hi / mainLines) * MAX_AXIS;
      lastBar.label = `${lastMembers.length} 个${lastMembers.every((item) => item.kind === "agent") ? " agent" : "动作"}`;
      lastBar.kind = groupKind(lastMembers);
      lastBar.title = lastMembers
        .map((item) => `${eventLabelOf(item)} L${item.line}`)
        .join(" · ");
      cursor = Math.max(cursor, line + 1);
      continue;
    }
    const lo = line;
    const bar: LaneBar = {
      id: `main-${bars.length}`,
      laneId: main.agentId,
      label: eventLabelOf(event),
      kind: groupKind([event]),
      start: ((lo - 1) / mainLines) * MAX_AXIS,
      end: (lo / mainLines) * MAX_AXIS,
      lo,
      hi: lo,
      span: 1,
      rail: true,
      title: `${eventLabelOf(event)} L${lo}（逻辑序，无真实时间戳）`,
    };
    bars.push(bar);
    lastWasGap = false;
    lastBar = bar;
    lastMembers = [event];
    cursor = Math.max(cursor, line + 1);
  }

  if (cursor <= mainLines) {
    pushGap(cursor, mainLines);
  }
  if (bars.length === 0) {
    pushGap(1, mainLines);
  }
  return bars;
}

function buildRailLabels(bars: LaneBar[]): LaneRailLabel[] {
  const labels = bars
    .filter((bar) => bar.rail)
    .map((bar) => {
      const text = `${bar.label}${bar.lo == null ? "" : bar.lo === bar.hi ? ` L${bar.lo}` : ` L${bar.lo}–${bar.hi}`}`;
      const width = Math.min(34, Math.max(5.5, (text.length * 6 + 14) / 780 * 100 + 0.4));
      return {
        id: bar.id,
        text,
        kind: (bar.kind === "skill" ? "is-skill" : "is-main") as LaneRailLabel["kind"],
        x: bar.start + (bar.end - bar.start) / 2,
        left: clamp(bar.start, 0.4, MAX_AXIS - width),
        row: 0,
        title: bar.title,
        width,
      };
    });
  const rowEnd = [-Infinity, -Infinity];
  labels.sort((left, right) => left.left - right.left).forEach((label) => {
    let row = rowEnd.findIndex((end) => label.left > end + 0.7);
    if (row < 0) {
      row = rowEnd[0]! <= rowEnd[1]! ? 0 : 1;
      label.left = Math.min(
        MAX_AXIS - label.width,
        Math.max(label.left, rowEnd[row]! + 0.7),
      );
    }
    label.row = row;
    rowEnd[row] = label.left + label.width;
  });
  return labels.map((label) => ({
    id: label.id,
    text: label.text,
    kind: label.kind,
    x: label.x,
    left: label.left,
    row: label.row,
    title: label.title,
  }));
}

function mainBarAt(bars: LaneBar[], line: number): LaneBar | null {
  return (
    bars.find(
      (bar) => bar.lo != null && bar.hi != null && line >= bar.lo && line <= bar.hi,
    ) ?? null
  );
}

function xOfLine(bars: LaneBar[], line: number, fallback: number): number {
  const bar = mainBarAt(bars, line);
  if (!bar) {
    return fallback;
  }
  const span = (bar.hi ?? 0) - (bar.lo ?? 0) + 1;
  const fraction = span <= 1 ? 0.5 : (line - (bar.lo ?? line) + 0.5) / span;
  const width = bar.end - bar.start;
  return bar.start + clamp(width * fraction, 0.1, Math.max(0.1, width - 0.1));
}

function buildSubBars(
  agent: SessionAgent,
  kind: LaneBarKind,
  start: number,
  end: number,
  cont: boolean,
): LaneBar[] {
  const events = [...agent.events].sort(
    (left, right) => left.line - right.line || left.messageOffset - right.messageOffset,
  );
  const contReason = cont ? "超出 100% 轴右缘，右缘延续标记表示未结束" : "";
  if (events.length === 0) {
    const known = agent.lines > 0;
    return [
      {
        id: "one",
        laneId: agent.agentId,
        label: known ? shortLabel(agent.desc || agent.label || agent.agentType || "agent") : "unknown",
        kind: known ? kind : "unknown",
        start,
        end: Math.max(start + MIN_BAR_WIDTH, end),
        lo: null,
        hi: null,
        span: Math.max(1, agent.lines),
        rail: false,
        title: known
          ? `${agent.desc || agent.label || "agent"} · ${agent.lines} 行（逻辑序占位，无真实时间戳）`
          : `${agent.desc || agent.label || "agent"} · 行数 unknown`,
        ...(known ? {} : { unknown: true }),
        ...(cont ? { cont: true, contReason } : {}),
      },
    ];
  }
  const slot = (end - start) / events.length;
  const inset = Math.min(0.4, slot * 0.1);
  return events.map((event, index) => {
    const barStart = start + index * slot + inset;
    const barEnd = Math.max(
      barStart + Math.min(MIN_BAR_WIDTH, slot * 0.8),
      start + (index + 1) * slot - inset,
    );
    const label = eventLabelOf(event);
    return {
      id: `event-${index}`,
      laneId: agent.agentId,
      label,
      kind: event.kind === "skill" ? "skill" : kind,
      start: barStart,
      end: barEnd,
      lo: event.line,
      hi: event.line,
      span: 1,
      rail: false,
      title: `${event.kind === "agent" ? "spawn " : ""}${label} · ${agent.label || "agent"} 内第 ${index + 1} 个动作（逻辑序占位，无真实时间戳）`,
      ...(cont ? { cont: true, contReason } : {}),
    };
  });
}

function reconcileLanes(
  lanes: Lane[],
  laneById: Map<string, Lane>,
  mainId: string,
): void {
  const childrenOf = new Map<string, Lane[]>();
  for (const lane of lanes) {
    if (!lane.parentId) {
      continue;
    }
    const list = childrenOf.get(lane.parentId) ?? [];
    list.push(lane);
    childrenOf.set(lane.parentId, list);
  }
  const visit = (lane: Lane) => {
    const children = childrenOf.get(lane.id) ?? [];
    children.forEach(visit);
    if (lane.id === mainId) {
      return;
    }
    const childMax = children.length ? Math.max(...children.map((child) => child.end)) : lane.end;
    if (childMax > lane.end + 0.01) {
      lane.end = Math.min(MAX_AXIS, childMax);
      const last = lane.bars.at(-1);
      if (last) {
        const previousEnd = last.end;
        last.end = lane.end;
        last.extended = true;
        last.title = `${last.title}；右缘从 ${previousEnd.toFixed(1)}% 延长到 ${lane.end.toFixed(1)}% 以容纳嵌套子 lane`;
      }
    }
    for (const child of children) {
      if (child.end <= lane.end + 0.01) {
        continue;
      }
      clampLaneEnd(child, lane.end);
    }
  };
  const main = laneById.get(mainId);
  if (main) {
    visit(main);
  }
}

function clampLaneEnd(lane: Lane, parentEnd: number): void {
  lane.end = Math.max(lane.start + MIN_BAR_WIDTH, Math.min(lane.end, parentEnd));
  for (const bar of lane.bars) {
    if (bar.end <= parentEnd + 0.01) {
      continue;
    }
    bar.end = Math.max(bar.start + 0.2, Math.min(bar.end, parentEnd));
    bar.cont = true;
    bar.contReason = "超出父 lane 末端，右缘为父 lane 边界";
    bar.title = `${bar.title}；${bar.contReason}`;
  }
  const last = lane.bars.at(-1);
  if (last) {
    lane.end = Math.max(lane.start + MIN_BAR_WIDTH, last.end);
  }
}

function buildBadCaseMarkers(
  badCases: readonly SessionBadCase[],
  byId: Map<string, SessionAgent>,
  main: SessionAgent,
  mainBars: LaneBar[],
  mainLines: number,
  selectedCaseId: string | null,
): BadCaseMarker[] {
  const eventLines = [...main.events]
    .map((event) => event.line)
    .filter((line) => Number.isFinite(line))
    .sort((left, right) => left - right);
  const rowLast = [-99, -99];
  const markers = badCases.map((badCase, index) => {
    const host = byId.get(badCase.anchor.agentId) ?? main;
    const anchored =
      badCase.anchor.eventIndex >= 0
        ? host.events[badCase.anchor.eventIndex]
        : undefined;
    const line = clamp(
      anchored?.line ?? (host.kind === "main" ? 1 : host.lines || 1),
      1,
      mainLines,
    );
    const bar = mainBarAt(mainBars, line);
    const inGap = bar?.kind === "gap";
    let gapNote: string | null = null;
    if (inGap) {
      const previous = eventLines.filter((candidate) => candidate < line).at(-1);
      const next = eventLines.find((candidate) => candidate > line);
      gapNote = `×${bar?.span ?? 0} 无触发区间（最近触发 ${
        previous != null ? `L${previous}` : "无"
      }${next != null ? ` → L${next}` : "，其后无事件"}）`;
    }
    return {
      badCaseId: badCase.badCaseId,
      index,
      title: badCase.title,
      line,
      x: clamp(xOfLine(mainBars, line, MAX_AXIS - 1.6), 1.6, 98.4),
      row: 0,
      selected: badCase.badCaseId === selectedCaseId,
      barId: bar?.id ?? null,
      inGap,
      gapNote,
      leadTop: 0,
      leadH: 0,
    };
  });
  markers
    .slice()
    .sort((left, right) => left.x - right.x)
    .forEach((marker) => {
      const gap0 = marker.x - rowLast[0]!;
      const gap1 = marker.x - rowLast[1]!;
      marker.row = gap0 > 3.6 ? 0 : gap1 > 3.6 ? 1 : gap0 >= gap1 ? 0 : 1;
      rowLast[marker.row] = Math.max(rowLast[marker.row]!, marker.x);
    });
  for (const marker of markers) {
    marker.leadTop = marker.row * 16 + 14;
    marker.leadH = Math.max(2, LANE_TOP + LANE_MAIN_BAR_TOP + 1 - LANE_AXIS_H - marker.leadTop);
  }
  return markers;
}

function assignCasesToLanes(
  markers: BadCaseMarker[],
  badCases: readonly SessionBadCase[],
  laneById: Map<string, Lane>,
  mainLane: Lane,
): void {
  const byCaseId = new Map(badCases.map((badCase) => [badCase.badCaseId, badCase]));
  for (const marker of markers) {
    const anchorId = byCaseId.get(marker.badCaseId)?.anchor.agentId ?? null;
    const host = (anchorId && laneById.get(anchorId)) || mainLane;
    host.cases.push(marker);
  }
}

function buildConcurrencyBands(lanes: Lane[]): ConcurrencyBand[] {
  const subs = lanes.filter((lane) => lane.depth > 0);
  if (subs.length === 0) {
    return [];
  }
  return [
    {
      left: Math.min(...subs.map((lane) => lane.start)),
      right: Math.max(...subs.map((lane) => lane.end)),
      top: Math.min(...subs.map((lane) => lane.top)) - 3,
      bottom: Math.max(...subs.map((lane) => lane.top)) + LANE_BAR_H + 14,
    },
  ];
}

function buildSpawnGroups(
  lanes: Lane[],
  laneById: Map<string, Lane>,
): LaneSpawnGroup[] {
  const groups = new Map<string, LaneSpawnGroup>();
  for (const lane of lanes) {
    if (!lane.parentId) {
      continue;
    }
    const parent = laneById.get(lane.parentId);
    if (!parent) {
      continue;
    }
    const key = `${lane.parentId}|${lane.parentBarId ?? lane.trigger.toFixed(2)}`;
    let group = groups.get(key);
    if (!group) {
      group = {
        key,
        parentId: lane.parentId,
        parentTop: parent.top,
        parentBarTop: parent.barTop,
        mergeX: lane.trigger,
        trunk: Math.max(parent.start + 0.4, lane.trigger - 1.1),
        adjacentOnly: true,
        lastY2: 0,
        members: [],
      };
      groups.set(key, group);
    }
    group.mergeX = Math.min(group.mergeX, lane.trigger);
    group.members.push({
      laneId: lane.id,
      trigger: lane.trigger,
      start: lane.start,
      top: lane.top,
      barTop: lane.barTop,
    });
    group.lastY2 = Math.max(group.lastY2, lane.top + lane.barTop + LANE_BAR_H);
  }
  return [...groups.values()].map((group) => ({
    ...group,
    trunk: Math.max(0.4, group.mergeX - 1.1),
    adjacentOnly: group.members.every(
      (member) =>
        member.top - group.parentTop === LANE_ROW_H ||
        member.top - group.parentTop === LANE_MAIN_ROW_H,
    ),
  }));
}
