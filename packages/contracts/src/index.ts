/**
 * Shared contracts between the API and the web app.
 *
 * API request and response types are generated from the checked-in FastAPI
 * OpenAPI snapshot. Prototype-only domain types remain explicit until the
 * corresponding API vertical slice replaces them.
 */

import type { components } from "./generated/api.js";

/** 服务交付阶段；后端配置、health 响应与前端展示共用这一封闭集合。 */
export const SERVICE_PHASES = ["scaffold", "demo", "live"] as const satisfies readonly ServicePhase[];

/** 服务交付阶段；前端只按此字段判断可用能力。 */
export type ServicePhase = components["schemas"]["ServicePhase"];

/** 数据库方言；后端配置、health 响应与前端展示共用这一封闭集合。 */
export const DATABASE_DIALECTS = ["sqlite", "mysql"] as const satisfies readonly DatabaseDialect[];

/** 数据库方言；前端按此字段选择展示文案。 */
export type DatabaseDialect = components["schemas"]["DatabaseDialect"];

/** 数据库健康摘要；失败时 `error` 只含脱敏错误类型与摘要。 */
export type DatabaseHealth = components["schemas"]["DatabaseHealthResponse"];

/** 健康检查响应；前端用它区分 API 可达与服务阶段。 */
export type HealthResponse = components["schemas"]["HealthResponse"];

/** Login request accepted by the identity API. */
export type LoginRequest = components["schemas"]["LoginRequest"];

/** Successful login payload containing only short-lived access credentials. */
export type LoginResponse = components["schemas"]["LoginResponse"];

/** Refresh payload after the httpOnly cookie has been rotated. */
export type RefreshResponse = components["schemas"]["RefreshResponse"];

/** Current-user password change payload. */
export type ChangePasswordRequest = components["schemas"]["ChangePasswordRequest"];

/** Single-use SSE authorization request bound to run topics and a replay cursor. */
export type TicketRequest = components["schemas"]["TicketRequest"];

/** Opaque short-lived SSE ticket and the topics it authorizes. */
export type EventTicketResponse = components["schemas"]["EventTicketResponse"];

/** User fields safe to retain in the browser. */
export type PublicUser = components["schemas"]["PublicUser"];

/** Durable job status returned by the REST source of truth. */
export type JobResponse = components["schemas"]["JobResponse"];

/** Durable acquisition progress shown by the quiet top bar. */
export type AcquisitionStatusResponse =
  components["schemas"]["AcquisitionStatusResponse"];

/** Result of a manual acquisition sync trigger. */
export type SyncTriggerResponse = components["schemas"]["SyncTriggerResponse"];

/** One root-session card shared by the list and overview API. */
export type SessionListItem = components["schemas"]["SessionListItem"];

/** Current-page root-session cards in server order. */
export type SessionListResponse = components["schemas"]["SessionListResponse"];

/** Whole-tree card statistics computed by the backend. */
export type SessionStats = components["schemas"]["SessionStats"];

/** Flat canonical Agent tree, events, and read-only problem anchors. */
export type SessionTree = components["schemas"]["SessionTree"];

/** One Agent row in the flat canonical Session tree. */
export type SessionAgent = components["schemas"]["SessionAgent"];

/** One skill, Agent, or workflow trigger inside an Agent chain. */
export type SessionEvent = components["schemas"]["SessionEvent"];

/** One anchored read-only problem returned with a Session tree. */
export type SessionBadCase = components["schemas"]["SessionBadCase"];

/** Stable host Agent and event index for a problem card. */
export type BadCaseAnchor = components["schemas"]["BadCaseAnchor"];

/** Reporter that originally supplied a problem report. */
export type BadCaseAgent = components["schemas"]["BadCaseAgent"];

/** FastAPI 真实 health 响应 fixture；前端类型测试不使用手写样例。 */
export { healthFixtures } from "./generated/health-fixtures.js";

/** 统一错误体；所有失败响应共享这一结构。 */
export type ErrorBody = components["schemas"]["ErrorBody"];

/** 稳定机器错误码；前端按 closed union 分支处理认证、限流与业务失败。 */
export type ErrorCode = components["schemas"]["ErrorCode"];

/** 统一错误响应；前端拦截器只读取这一外壳。 */
export type ErrorResponse = components["schemas"]["ErrorResponse"];

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
