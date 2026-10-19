/**
 * Shared contracts between the API and the web app.
 *
 * Domain types are intentionally kept out of the scaffold. They will be added
 * together with the corresponding API vertical slice.
 */

/** 服务交付阶段；随垂直切片推进扩展，前端只按此字段判断可用能力。 */
export type ServicePhase = "scaffold";

/** 健康检查响应；前端用它区分 API 可达与服务阶段。 */
export interface HealthResponse {
  ok: boolean;
  service: "harness-evolution";
  phase: ServicePhase;
}

export type {
  AgentKind,
  AgentNode,
  AgentStats,
  AgentStatus,
  AttributionTarget,
  EvidenceRef,
  FamilyStats,
  Finding,
  FindingAttribution,
  FindingCategory,
  FindingSeverity,
  RolloutId,
  RolloutSegment,
  SessionFamily,
  SessionFamilySnapshot,
  SkillUse,
  SkillUseOccurrence,
  SnapshotDiagnostic,
  SnapshotDiagnosticCode,
  ThreadId,
  TimelineItem,
  TimelineItemDetails,
  TimelineItemKind,
} from "./session-family.js";
