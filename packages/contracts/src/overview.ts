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

/** One filtered page of this workspace's reported cases. */
export type OverviewBadCaseListResponse =
  components["schemas"]["OverviewBadCaseListResponse"];
