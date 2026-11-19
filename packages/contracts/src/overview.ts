/**
 * Workspace overview contracts from the V2 design.
 *
 * Every payload type is generated from the FastAPI OpenAPI snapshot; this
 * module only re-exports them under stable names and keeps the filter unions.
 */

import type { components } from "./generated/api.js";

/** Quick overview windows the filter bar offers. */
export type OverviewRange = 7 | 30 | 90;

/** Trend granularity requested by the page; the response states the effective one. */
export type OverviewGrain = "day" | "week" | "month";

/** Bad-case type filter accepted by the overview list. */
export type OverviewBadCaseType = "all" | "self" | "discovery";

/** One resolved inclusive overview window. */
export type OverviewWindow = components["schemas"]["OverviewWindow"];

/** Overview counters; `quota`/`used` ignore the window and every filter. */
export type OverviewTotals = components["schemas"]["OverviewTotals"];

/** One workspace overview header: window, totals, and object options. */
export type OverviewSummary = components["schemas"]["OverviewSummary"];

/** One continuous, zero-filled trend bucket. */
export type OverviewTrendBucket = components["schemas"]["TrendBucket"];

/** The continuous trend series plus the grain actually used. */
export type OverviewTrendResponse = components["schemas"]["TrendResponse"];

/** One object's share of the window, split by bad-case type. */
export type OverviewSourceRow = components["schemas"]["SourceRow"];

/** Source distribution ordered by total descending, then object name. */
export type OverviewSourceListResponse =
  components["schemas"]["SourceListResponse"];

/** One row of the filtered workspace bad-case list. */
export type BadCaseListItem = components["schemas"]["BadCaseListItem"];

/** Derived trace readiness for one reported bad case. */
export type BadCaseTraceStatus =
  components["schemas"]["BadCaseTraceStatus"];

/** One filtered page of this workspace's reported cases. */
export type OverviewBadCaseListResponse =
  components["schemas"]["OverviewBadCaseListResponse"];

/** Attribution state of one potential case under one target version. */
export type TargetState = "attributed" | "nonTarget" | "unanalyzed";

/** Object type configured for one evolution target. */
export type TargetObjectType = "skill" | "agent" | "knowledge";

/** Window-wide target totals shown by the target stat strip. */
export type TargetOverviewSummary =
  components["schemas"]["TargetOverviewSummary"];

/** One version's canonical key plus the ref/commit used for display. */
export type TargetVersionOption =
  components["schemas"]["TargetVersionOption"];

/** One target's potential cases and their three-state split. */
export type TargetOverviewItem = components["schemas"]["TargetOverviewItem"];

/** One evolvable-sorted page of targets plus the workspace-wide summary. */
export type TargetOverviewListResponse =
  components["schemas"]["TargetOverviewListResponse"];

/** One target's contribution to a trend bucket. */
export type TargetTrendByTarget =
  components["schemas"]["TargetTrendByTarget"];

/** One continuous, zero-filled three-state target trend bucket. */
export type TargetTrendBucket = components["schemas"]["TargetTrendBucket"];

/** The bucket-time policy the target trend actually applied. */
export type TargetTrendMeta = components["schemas"]["TargetTrendMeta"];

/** The target trend series plus its effective grain. */
export type TargetTrendResponse = components["schemas"]["TargetTrendResponse"];

/** One potential case under one target version with its attribution state. */
export type TargetCaseItem = components["schemas"]["TargetCaseItem"];

/** One filtered page of potential cases plus its authoritative total. */
export type TargetCaseListResponse =
  components["schemas"]["TargetCaseListResponse"];

/** The configured target a detail card is about and every version it has. */
export type TargetDetailTarget = components["schemas"]["TargetDetailTarget"];

/** The detail card's four counters. */
export type TargetDetailStats = components["schemas"]["TargetDetailStats"];

/** One version's contribution inside the selected detail scope. */
export type TargetDetailVersion =
  components["schemas"]["TargetDetailVersion"];

/** One reported source inside the selected detail scope. */
export type TargetDetailSource = components["schemas"]["TargetDetailSource"];

/** One target's independent version and source analysis. */
export type TargetDetailResponse =
  components["schemas"]["TargetDetailResponse"];
