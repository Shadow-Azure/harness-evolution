/**
 * Shared contracts between the API and the web app.
 *
 * Domain types are intentionally kept out of the scaffold. They will be added
 * together with the corresponding API vertical slice.
 */

/** 服务交付阶段；后端配置、health 响应与前端展示共用这一封闭集合。 */
export const SERVICE_PHASES = ["scaffold", "demo", "live"] as const;

/** 服务交付阶段；前端只按此字段判断可用能力。 */
export type ServicePhase = (typeof SERVICE_PHASES)[number];

/** 数据库方言；后端配置、health 响应与前端展示共用这一封闭集合。 */
export const DATABASE_DIALECTS = ["sqlite", "mysql"] as const;

/** 数据库方言；前端按此字段选择展示文案。 */
export type DatabaseDialect = (typeof DATABASE_DIALECTS)[number];

/** 数据库健康摘要；失败时 `error` 只含脱敏错误类型与摘要。 */
export interface DatabaseHealth {
  dialect: DatabaseDialect;
  ok: boolean;
  latencyMs: number;
  error?: string;
}

/** 健康检查响应；前端用它区分 API 可达与服务阶段。 */
export interface HealthResponse {
  ok: boolean;
  service: "harness-evolution";
  phase: ServicePhase;
  version: string;
  db: DatabaseHealth;
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
