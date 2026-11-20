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

/** Small unpaginated administrator user list used to seed workspace admins. */
export type UserListResponse = components["schemas"]["UserListResponse"];

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
/** Complete read-only problem returned by Session and deep-link routes. */
export type BadCase = components["schemas"]["BadCase"];
/** Session problem list response. */
export type BadCaseListResponse = components["schemas"]["BadCaseListResponse"];
/** Five-state attribution view returned by the analysis route. */
export type BadCaseAnalysis = components["schemas"]["BadCaseAnalysis"];
/** Root-cause report with validated reverse source links. */
export type ProbeReport = components["schemas"]["ProbeReport"];
/** One object/revision attribution shown in the folded error-detail list. */
export type AttributionItem = components["schemas"]["AttributionItem"];
/** One attribution with reasoning, warnings and trigger-point comparison. */
export type AttributionDetail = components["schemas"]["AttributionDetail"];
/** One deterministic newest-first page of a case's attributions. */
export type AttributionPage = components["schemas"]["AttributionPage"];
/** Session root-cause report list response. */
export type ProbeListResponse = components["schemas"]["ProbeListResponse"];

/** One complete run-list card grouped by backend state. */
export type EvolutionRunCard = components["schemas"]["EvolutionRunCard"];

/** Running and history groups already ordered by the backend. */
export type EvolutionRunList = components["schemas"]["EvolutionRunList"];

/** Complete run detail shell with workspace and backend-owned step states. */
export type EvolutionRunDetail = components["schemas"]["EvolutionRunDetail"];

/** Accepted manual retry for one blocked full run. */
export type EvolutionRetryAccepted =
  components["schemas"]["EvolutionRetryAccepted"];

/** One durable execution-log event shared by REST replay and SSE. */
export type EvolutionRunEvent = components["schemas"]["EvolutionRunEvent"];

/** Sanitized error attached to one execution-log event. */
export type EvolutionRunEventError =
  components["schemas"]["EvolutionRunEventError"];

/** One stable page of durable execution-log events. */
export type EvolutionRunEventPage =
  components["schemas"]["EvolutionRunEventPage"];

/** Durable event severity used by the execution-log filter. */
export type EvolutionRunEventLevel = EvolutionRunEvent["level"];

/** Repository and worktree state rendered on the run detail. */
export type EvolutionRunWorkspace =
  components["schemas"]["EvolutionRunWorkspace"];

/** One backend-owned stepper node from the run detail shell. */
export type EvolutionRunStep = components["schemas"]["EvolutionRunStep"];

/** Backend-owned progress, stage copy, rounds, and accepted count. */
export type EvolutionRunProgress = components["schemas"]["EvolutionRunProgress"];

/** Backend-normalized run statistics and attribution distribution. */
export type EvolutionRunStats = components["schemas"]["EvolutionRunStats"];

/** Terminal evaluation summary shown for completed runs. */
export type EvolutionRunFinal = components["schemas"]["EvolutionRunFinal"];

/** Evolution target configuration accepted by create and update. */
export type EvolutionTargetWrite = components["schemas"]["EvolutionTargetWrite"];

/** Persisted evolution target configuration. */
export type EvolutionTarget = components["schemas"]["EvolutionTarget"];

/** Complete evolution target configuration list. */
export type EvolutionTargetList = components["schemas"]["EvolutionTargetList"];

/** Remote versions and default reference for one target. */
export type EvolutionTargetVersions =
  components["schemas"]["EvolutionTargetVersions"];

/** One immutable Attribution Skill revision visible to a workspace. */
export type AttributionSkillRevision =
  components["schemas"]["app__service__evolution__attribution_skills__AttributionSkillRevision"];

/** Platform and workspace Attribution Skill revisions visible to a workspace. */
export type AttributionSkillList = components["schemas"]["AttributionSkillList"];

/** Effective target Skill plus target/workspace/platform precedence source. */
export type EffectiveAttributionSkill =
  components["schemas"]["EffectiveAttributionSkill"];

/** Request selecting one immutable Attribution Skill revision. */
export type AttributionSkillBindingWrite =
  components["schemas"]["AttributionSkillBindingWrite"];

/** Persisted isolated Golden Set result for one immutable Skill revision. */
export type AttributionQualityEvaluation =
  components["schemas"]["AttributionQualityEvaluation"];

/** Human acceptance or rejection backed by one exact shadow evaluation. */
export type AttributionQualityDecisionWrite =
  components["schemas"]["AttributionQualityDecisionWrite"];

/** Append-only evaluation and promotion audit trail. */
export type AttributionQualityHistory =
  components["schemas"]["AttributionQualityHistory"];

/** Human reason attached to a workspace-default rollback. */
export type AttributionRollbackWrite =
  components["schemas"]["AttributionRollbackWrite"];

/** One built-in or uploaded attribution Skill ZIP package. */
export type AttributionSkillPackage =
  components["schemas"]["AttributionSkillPackage"];

/** Workspace packages plus the currently effective prompt. */
export type SkillResourceDetail = components["schemas"]["SkillResourceDetail"];

/** Immutable built-in and uploaded resources visible to this workspace. */
export type AttributionSkillPackageList =
  components["schemas"]["AttributionSkillPackageList"];

/** Sanitized metrics for one durable attribution batch. */
export type AttributionJobObservation =
  components["schemas"]["AttributionJobObservation"];

/** One durable attribution execution and its retry/cancellation state. */
export type AttributionJobView = components["schemas"]["AttributionJobView"];

/** Newest-first attribution executions for one evolution run. */
export type AttributionJobList = components["schemas"]["AttributionJobList"];

/** One enabled target exposed to the wizard catalog. */
export type CatalogTarget = components["schemas"]["CatalogTarget"];

/** Enabled evolution targets grouped by object type. */
export type CatalogTargets = components["schemas"]["CatalogTargets"];

/** One normalized model and its usage counts. */
export type CatalogModel = components["schemas"]["CatalogModel"];

/** Normalized model catalog. */
export type CatalogModels = components["schemas"]["CatalogModels"];

/** Wizard filter condition shared by probe preview and launch endpoints. */
export type ProbeQueryRequest = components["schemas"]["ProbeQueryRequest"];

/** Hit statistics shown by wizard step 2. */
export type ProbeHitSummary = components["schemas"]["ProbeHitSummary"];

/** One analyzed probe row rendered by wizard step 2. */
export type ProbePreviewItem = components["schemas"]["ProbePreviewItem"];

/** Complete probe preview payload for wizard step 2. */
export type ProbeQueryResult = components["schemas"]["ProbeQueryResult"];

/** Raw potential policy switches accepted by preview and launch endpoints. */
export type PotentialPolicy = components["schemas"]["PotentialPolicy"];

/** Step 2 condition plus the page of Sessions associated with the target. */
export type SessionsPreviewRequest =
  components["schemas"]["SessionsPreviewRequest"];

/** Non-overlapping Session partition shown in wizard step 2. */
export type SessionPreviewSummary =
  components["schemas"]["SessionPreviewSummary"];

/** One associated Session row rendered by wizard step 2. */
export type SessionPreviewItem = components["schemas"]["SessionPreviewItem"];

/** Paged associated Session projection for wizard step 2. */
export type SessionPreviewResult =
  components["schemas"]["SessionPreviewResult"];

/** Step 3 condition plus the policy and potential page. */
export type PotentialPreviewRequest =
  components["schemas"]["PotentialPreviewRequest"];

/** Closed hit-reason distribution shown in wizard step 3. */
export type PotentialReasonCounts =
  components["schemas"]["PotentialReasonCounts"];

/** Case and policy counts shown in wizard step 3. */
export type PotentialPreviewSummary =
  components["schemas"]["PotentialPreviewSummary"];

/** One policy-included bad case row rendered by wizard step 3. */
export type PotentialPreviewItem = components["schemas"]["PotentialPreviewItem"];

/** Paged potential case projection for wizard step 3. */
export type PotentialPreviewResult =
  components["schemas"]["PotentialPreviewResult"];

/** Step 4 condition with the cache switch and no pagination. */
export type AttributionPreviewRequest =
  components["schemas"]["AttributionPreviewRequest"];

/** Cache reuse and non-target reference counts for wizard step 4. */
export type AttributionPreviewSummary =
  components["schemas"]["AttributionPreviewSummary"];

/** Read-only attribution preview returned by wizard step 4. */
export type AttributionPreviewResult =
  components["schemas"]["AttributionPreviewResult"];

/** Asynchronous launch acceptance returned by run and preview endpoints. */
export type RunAccepted = components["schemas"]["RunAccepted"];

/** Backend-owned selection snapshot of one evolution run. */
export type EvolutionStepRange = components["schemas"]["EvolutionStepRange"];

/** Backend-owned Session association projection of one evolution run. */
export type EvolutionStepSessions = components["schemas"]["EvolutionStepSessions"];

/** Backend-owned potential bad-case projection of one evolution run. */
export type EvolutionStepPotential = components["schemas"]["EvolutionStepPotential"];

/** Backend-owned attribution projection of one evolution run. */
export type EvolutionStepAttribution = components["schemas"]["EvolutionStepAttribution"];

/** Backend-owned cluster projection of one evolution run. */
export type EvolutionStepClusters = components["schemas"]["EvolutionStepClusters"];

/** Backend-owned iteration projection of one evolution run. */
export type EvolutionStepIteration = components["schemas"]["EvolutionStepIteration"];

/** Backend-owned terminal evaluation projection of one evolution run. */
export type EvolutionStepFinal = components["schemas"]["EvolutionStepFinal"];

/** One key-discriminated response from the seven evolution-step endpoints. */
export type EvolutionStep =
  | EvolutionStepRange
  | EvolutionStepSessions
  | EvolutionStepPotential
  | EvolutionStepAttribution
  | EvolutionStepClusters
  | EvolutionStepIteration
  | EvolutionStepFinal;

/** Stable semantic key shared by one evolution-step route and payload. */
export type EvolutionStepKey = EvolutionStep["key"];

/** Backend-owned status for one step in the evolution stepper. */
export type EvolutionStepStatus = EvolutionStep["status"];

/** Selection snapshot and headline counts of the range step. */
export type StepRangeCondition = components["schemas"]["StepRangeCondition"];
/** Headline Session, bad-case, and potential counts of the range step. */
export type StepRangeStats = components["schemas"]["StepRangeStats"];
/** Selection snapshot and headline counts rendered by the range step. */
export type StepRangePayload = components["schemas"]["StepRangePayload"];

/** Session partition and one associated Session row. */
export type StepSessionsSummary = components["schemas"]["StepSessionsSummary"];
/** One associated Session row with its trigger time and case counts. */
export type StepSessionRow = components["schemas"]["StepSessionRow"];
/** Paged Session association payload rendered by the sessions step. */
export type StepSessionsPayload = components["schemas"]["StepSessionsPayload"];

/** Potential summary and one included bad-case row. */
export type StepPotentialSummary = components["schemas"]["StepPotentialSummary"];
/** One included potential bad-case row with its hit reason and order state. */
export type StepPotentialRow = components["schemas"]["StepPotentialRow"];
/** Paged potential bad-case payload rendered by the potential step. */
export type StepPotentialPayload = components["schemas"]["StepPotentialPayload"];

/** Attribution summary and one case conclusion. */
export type StepAttributionSummary = components["schemas"]["StepAttributionSummary"];
/** One case attribution conclusion with its cached/fresh source. */
export type StepAttributionRow = components["schemas"]["StepAttributionRow"];
/** Attribution summary and per-case rows rendered by the attribution step. */
export type StepAttributionPayload = components["schemas"]["StepAttributionPayload"];

/** One ranked cluster with its source cases. */
export type StepCluster = components["schemas"]["StepCluster"];
/** One source bad case inside a cluster or iteration round. */
export type StepClusterCase = components["schemas"]["StepClusterCase"];
/** Severity-ordered clusters rendered by the clusters step. */
export type StepClustersPayload = components["schemas"]["StepClustersPayload"];

/** One execution round rendered by the iteration step. */
export type StepRound = components["schemas"]["StepRound"];

/** Pushed candidate ref and commit backing one iteration round. */
export type StepCandidate = components["schemas"]["StepCandidate"];

/** Placeholder or generated patch preview stored with one round. */
export type StepRoundPatch = components["schemas"]["StepRoundPatch"];

/** Candidate push outcome stored with one round. */
export type StepRoundPush = components["schemas"]["StepRoundPush"];

/** External evaluation state stored with one round. */
export type StepRoundEval = components["schemas"]["StepRoundEval"];

/** Amended run-branch commit recorded after accepting a candidate. */
export type StepFinalCommit = components["schemas"]["StepFinalCommit"];

/** One accepted round inside the terminal modification list. */
export type StepFinalChange = components["schemas"]["StepFinalChange"];

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

export type {
  BadCaseListItem,
  BadCaseTraceStatus,
  OverviewBadCaseListResponse,
  OverviewBadCaseType,
  OverviewGrain,
  OverviewRange,
  OverviewSourceListResponse,
  OverviewSourceRow,
  OverviewSummary,
  OverviewTotals,
  OverviewTrendBucket,
  OverviewTrendResponse,
  OverviewWindow,
  TargetCaseItem,
  TargetCaseListResponse,
  TargetDetailResponse,
  TargetDetailSource,
  TargetDetailStats,
  TargetDetailTarget,
  TargetDetailVersion,
  TargetObjectType,
  TargetOverviewItem,
  TargetOverviewListResponse,
  TargetOverviewSummary,
  TargetState,
  TargetTrendBucket,
  TargetVersionOption,
  TargetTrendByTarget,
  TargetTrendMeta,
  TargetTrendResponse,
} from "./overview.js";

export type {
  SessionPayload,
  SessionWorkspace,
  Workspace,
  WorkspaceAdmin,
  WorkspaceCreateRequest,
  WorkspaceCredential,
  WorkspaceCredentialCreated,
  WorkspaceCredentialListResponse,
  WorkspaceListResponse,
  WorkspaceMember,
  WorkspaceMemberCandidate,
  WorkspaceMemberCandidateListResponse,
  WorkspaceMemberCreateRequest,
  WorkspaceMemberListResponse,
  WorkspaceMemberRole,
  WorkspaceMemberUpdateRequest,
  WorkspaceRole,
  WorkspaceUpdateRequest,
} from "./workspaces.js";
