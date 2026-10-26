import type { SessionAgent, SessionBadCase, SessionEvent, SessionTree } from "@harness/contracts";

/** Measures rendered text width for deterministic pill geometry. */
export type MeasureText = (text: string, font: string) => number;

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
      evIdx: number;
      line: number;
      w: number;
    };

/** Horizontal trigger chain rendered inside one Agent node. */
export interface AgentChain {
  items: ChainItem[];
  offsets: number[];
  width: number;
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
  kind: "self-skill" | "self-agent" | "discovery" | "fallback";
  side: "below" | "above" | "left" | "right";
  x: number;
  y: number;
}

/** Complete deterministic output of the pure graph layout. */
export interface AgentGraphLayout {
  nodes: AgentLayoutNode[];
  edges: AgentLayoutEdge[];
  anchors: BadCaseAnchorDescriptor[];
  diagnostics: LayoutDiagnostic[];
  branchSegments: BranchSegment[];
}

/** Inputs accepted by `buildGraph`. */
export interface BuildGraphOptions {
  expanded?: Iterable<string>;
  measureText?: MeasureText;
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
