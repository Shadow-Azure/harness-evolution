import type {
  BadCase,
  SessionAgent,
  SessionBadCase,
  SessionEvent,
  SessionTree,
} from "@harness/contracts";

/** Measures rendered text width for deterministic pill geometry. */
export type MeasureText = (text: string, font: string) => number;

/** Parent relation evidence exposed on one Agent trigger event. */
export type RelationConfidence = NonNullable<SessionEvent["relationConfidence"]>;

/** One compressed-message or trigger item in an Agent chain. */
export type ChainItem =
  | {
      kind: "gap";
      n: number;
      w: number;
    }
  | {
      kind: SessionEvent["kind"];
      name: string;
      title?: string;
      evIdx: number;
      line: number;
      w: number;
      synthetic?: boolean;
    };

/** Horizontal trigger chain rendered inside one Agent node. */
export interface AgentChain {
  items: ChainItem[];
  offsets: number[];
  width: number;
}

/** Trigger-pill handle occupancy derived from rendered graph edges. */
export interface TriggerConnection {
  above?: boolean;
  below?: boolean;
}

/** Data attached to one Agent or collapse layout node. */
export interface AgentLayoutNodeData {
  label: string;
  kind: "root" | "sub" | "wf" | "collapse";
  w: number;
  boxW: number;
  visualW: number;
  lines: number;
  desc: string;
  chain: AgentChain;
  agentId: string | null;
  parentAgentId: string | null;
  parentForCollapse?: string;
  active?: boolean;
  activeEvidence?: number | null;
  triggerConnections?: Record<number, TriggerConnection>;
  relationConfidence?: RelationConfidence | null;
  completionWarning?: string | null;
}

/** DOM-independent Vue Flow-compatible node. */
export interface AgentLayoutNode {
  id: string;
  type: "agent" | "collapse";
  position: { x: number; y: number };
  data: AgentLayoutNodeData;
}

/** DOM-independent Vue Flow-compatible edge. */
export interface AgentLayoutEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle: string;
  targetHandle: string;
  type: "orth";
  data: { idx: number; trunkX: number };
  style: { stroke: string; strokeWidth: number };
}

/** Data rendered by one problem-card node. */
export interface BadCaseLayoutNodeData {
  badCaseId: string;
  shortId: string;
  title: string;
  width: number;
  degraded: boolean;
  /** Optional anchor audit label, e.g. `后处理` for a post-process anchor. */
  anchorLabel?: string | null;
  active?: boolean;
}

/** DOM-independent problem-card node. */
export interface BadCaseLayoutNode {
  id: string;
  type: "badcase";
  position: { x: number; y: number };
  data: BadCaseLayoutNodeData;
}

/** Problem-card connector kind selected from the API anchor. */
export type BadCaseEdgeType = "badcase" | "discovery" | "trigger";

/** DOM-independent problem-card edge. */
export interface BadCaseLayoutEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle: string;
  targetHandle: string;
  type: BadCaseEdgeType;
  data: {
    badCaseId: string;
    side: BadCaseAnchorDescriptor["side"];
  };
  style: {
    stroke: string;
    strokeWidth: number;
    strokeDasharray?: string;
  };
}

/** Stable layout diagnostic suitable for logs and tests. */
export interface LayoutDiagnostic {
  code:
    | "MISSING_MAIN"
    | "DUPLICATE_MAIN"
    | "DUPLICATE_AGENT"
    | "ORPHAN_PARENT"
    | "PARENT_CYCLE"
    | "MISSING_PARENT_EVENT"
    | "MISSING_ANCHOR_AGENT";
  agentId: string | null;
  message: string;
}

/** Vertical branch channel used for finding-side collision checks. */
export interface BranchSegment {
  source: string;
  target: string;
  x: number;
  y1: number;
  y2: number;
}

/** Position metadata m4 consumes without rendering finding cards in m3-02. */
export interface BadCaseAnchorDescriptor {
  badCaseId: string;
  hostAgentId: string;
  eventIndex: number;
  kind:
    | "self-skill"
    | "self-agent"
    | "discovery"
    | "post-process"
    | "fallback"
    | "hidden";
  side: "below" | "above" | "left" | "right";
  x: number;
  y: number;
  /** Audit label shown on the card when the anchor has no event coordinate. */
  anchorLabel?: string | null;
}

/** Complete deterministic output of the pure graph layout. */
export interface AgentGraphLayout {
  nodes: AgentLayoutNode[];
  edges: AgentLayoutEdge[];
  badCaseNodes: BadCaseLayoutNode[];
  badCaseEdges: BadCaseLayoutEdge[];
  anchors: BadCaseAnchorDescriptor[];
  diagnostics: LayoutDiagnostic[];
  branchSegments: BranchSegment[];
}

/** Inputs accepted by `buildGraph`. */
export interface BuildGraphOptions {
  expanded?: Iterable<string>;
  measureText?: MeasureText;
  problemDetails?: readonly BadCase[];
}

/** Inputs accepted by `badCaseAnchors`. */
export interface BadCaseAnchorOptions {
  nodes: AgentLayoutNode[];
  agents: SessionAgent[];
  badCases: SessionBadCase[];
  branchSegments: BranchSegment[];
}

/** Narrow tree subset consumed by the pure layout. */
export type LayoutTree = Pick<SessionTree, "sessionId" | "agents" | "badCases">;

/** One trigger event inside an Agent chain, re-exported for lane consumers. */
export type TreeEvent = SessionEvent;

/** Kind of a lane bar: main trigger, nested trigger, skill, or no-trigger gap. */
export type LaneBarKind =
  | "main"
  | "sub"
  | "sub2"
  | "skill"
  | "gap"
  | "summary"
  | "unknown";

/** One horizontal interval on a lane; `start`/`end` are percentages of the log axis. */
export interface LaneBar {
  id: string;
  laneId: string;
  label: string;
  kind: LaneBarKind;
  start: number;
  end: number;
  lo: number | null;
  hi: number | null;
  span: number;
  rail: boolean;
  title: string;
  unknown?: boolean;
  cont?: boolean;
  contReason?: string;
  extended?: boolean;
}

/** Trigger label placed above the main lane without affecting interval width. */
export interface LaneRailLabel {
  id: string;
  text: string;
  kind: "is-main" | "is-skill";
  x: number;
  left: number;
  row: number;
  title: string;
}

/** One bad-case marker pinned above the main lane. */
export interface BadCaseMarker {
  badCaseId: string;
  index: number;
  title: string;
  line: number;
  x: number;
  row: number;
  selected: boolean;
  /** Audit label such as `后处理` when the anchor has no event coordinate. */
  anchorLabel: string | null;
  barId: string | null;
  inGap: boolean;
  gapNote: string | null;
  leadTop: number;
  leadH: number;
}

/** One lane = one agent invocation, identified by its `A1/A1.1` path. */
export interface Lane {
  id: string;
  path: string;
  depth: number;
  label: string;
  full: string;
  top: number;
  start: number;
  end: number;
  lines: number;
  trigger: number;
  parentId: string | null;
  parentBarId: string | null;
  kind: SessionAgent["kind"];
  state: "" | "concurrent" | "unknown";
  bars: LaneBar[];
  events: TreeEvent[];
  cases: BadCaseMarker[];
  railLabels: LaneRailLabel[];
  barTop: number;
  trackH: number;
  rowH: number;
}

/** Horizontal band covering every concurrent sub lane's true interval. */
export interface ConcurrencyBand {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

/** One spawn trunk shared by siblings triggered from the same parent bar. */
export interface LaneSpawnGroup {
  key: string;
  parentId: string;
  parentTop: number;
  parentBarTop: number;
  mergeX: number;
  trunk: number;
  adjacentOnly: boolean;
  lastY2: number;
  members: Array<{
    laneId: string;
    trigger: number;
    start: number;
    top: number;
    barTop: number;
  }>;
}

/** Stable lane-model diagnostic suitable for logs and tests. */
export interface LaneDiagnostic {
  code:
    | "MISSING_MAIN"
    | "DUPLICATE_MAIN"
    | "DUPLICATE_AGENT"
    | "ORPHAN_PARENT"
    | "PARENT_CYCLE";
  agentId: string | null;
  message: string;
}

/** Complete deterministic output of the pure lane DAG model. */
export interface LaneModel {
  lanes: Lane[];
  width: number;
  height: number;
  mainLines: number;
  caseMarkers: BadCaseMarker[];
  concurrencyBands: ConcurrencyBand[];
  spawnGroups: LaneSpawnGroup[];
  diagnostics: LaneDiagnostic[];
}

/** Normalized canvas transform used by the lane viewport. */
export interface LaneViewport {
  x: number;
  y: number;
  k: number;
}

/** Height of the 0–100 log-axis ruler above the lanes, in CSS pixels. */
export const LANE_AXIS_H = 18;

/** Height of the bad-case marker row between the ruler and the first lane. */
export const LANE_CASE_ROW = 28;

/** Top offset of the first lane; ruler plus marker row. */
export const LANE_TOP = LANE_AXIS_H + LANE_CASE_ROW;

/** Row height of the main lane, which carries the trigger-label rail. */
export const LANE_MAIN_ROW_H = 70;

/** Row height of every non-main lane. */
export const LANE_ROW_H = 44;

/** Bar top offset inside a non-main lane track. */
export const LANE_BAR_TOP = 4;

/** Bar top offset inside the main lane track, below the trigger-label rail. */
export const LANE_MAIN_BAR_TOP = 34;

/** Bar height used by bars and spawn-join geometry. */
export const LANE_BAR_H = 20;

/** Track height of a non-main lane. */
export const LANE_TRACK_H = 30;

/** Track height of the main lane, including its trigger-label rail. */
export const LANE_MAIN_TRACK_H = 56;
