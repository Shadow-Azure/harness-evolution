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

/** FastAPI 真实 health 响应 fixture；前端类型测试不使用手写样例。 */
export { healthFixtures } from "./generated/health-fixtures.js";

/** 统一错误体；所有失败响应共享这一结构。 */
export type ErrorBody = components["schemas"]["ErrorBody"];

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
