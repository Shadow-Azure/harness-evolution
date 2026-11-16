import type {
  OverviewBadCaseType,
  OverviewGrain,
  OverviewRange,
} from "@harness/contracts";

/** Quick range choices plus the custom window the filter bar can open. */
export type OverviewRangeChoice = OverviewRange | "custom";

/** Everything the overview URL owns; the page derives its queries from it. */
export type OverviewUrlState = {
  tab: "cases";
  range: OverviewRangeChoice;
  from: string;
  to: string;
  grain: OverviewGrain;
  objects: string[];
  page: number;
  type: OverviewBadCaseType;
};

/** Result of parsing one raw route query. */
export type OverviewParsedQuery = {
  state: OverviewUrlState;
  /** True when the URL asked for the M11 targets tab. */
  targetsRequested: boolean;
  /** True when the raw query was not already in canonical form. */
  sanitized: boolean;
};

/** Default landing state: 90-day window, weekly grain, no object filter. */
export const DEFAULT_OVERVIEW_STATE: OverviewUrlState = {
  tab: "cases",
  range: 90,
  from: "",
  to: "",
  grain: "week",
  objects: [],
  page: 1,
  type: "all",
};

const RANGE_VALUES = new Set([7, 30, 90]);
const GRAIN_VALUES = new Set<OverviewGrain>(["day", "week", "month"]);
const TYPE_VALUES = new Set<OverviewBadCaseType>(["all", "self", "discovery"]);
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

function firstValue(value: unknown): string | null {
  if (typeof value === "string") return value;
  if (Array.isArray(value) && typeof value[0] === "string") return value[0];
  return null;
}

function validDate(value: string | null): string {
  if (!value || !DATE_PATTERN.test(value)) return "";
  const [year, month, day] = value.split("-").map(Number) as [
    number,
    number,
    number,
  ];
  const parsed = new Date(Date.UTC(year, month - 1, day));
  if (
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() !== month - 1 ||
    parsed.getUTCDate() !== day
  ) {
    return "";
  }
  return value;
}

function parsePage(value: string | null): number {
  if (!value || !/^\d+$/.test(value)) return 1;
  const page = Number(value);
  return Number.isSafeInteger(page) && page >= 1 ? page : 1;
}

function parseObjects(value: string | null): string[] {
  if (!value) return [];
  const seen = new Set<string>();
  for (const raw of value.split(",")) {
    const name = raw.trim();
    if (name) seen.add(name);
  }
  return [...seen];
}

function parseRange(
  rawRange: string | null,
  from: string,
  to: string,
): { range: OverviewRangeChoice; from: string; to: string } {
  if (rawRange === "custom") {
    if (from && to && from <= to) return { range: "custom", from, to };
    return { range: DEFAULT_OVERVIEW_STATE.range, from: "", to: "" };
  }
  const numeric = rawRange === null ? null : Number(rawRange);
  if (numeric !== null && RANGE_VALUES.has(numeric)) {
    return { range: numeric as OverviewRange, from: "", to: "" };
  }
  if (from && to && from <= to) return { range: "custom", from, to };
  return { range: DEFAULT_OVERVIEW_STATE.range, from: "", to: "" };
}

/**
 * Normalize one raw route query into the canonical overview state.
 * @param query Raw `route.query` object.
 * @returns The parsed state plus the tab/sanitization flags the page needs.
 */
export function parseOverviewQuery(
  query: Record<string, unknown>,
): OverviewParsedQuery {
  const rawTab = firstValue(query.tab);
  const targetsRequested = rawTab === "targets";

  const from = validDate(firstValue(query.from));
  const to = validDate(firstValue(query.to));
  const { range, from: windowFrom, to: windowTo } = parseRange(
    firstValue(query.range),
    from,
    to,
  );

  const rawGrain = firstValue(query.grain);
  const grain =
    rawGrain && GRAIN_VALUES.has(rawGrain as OverviewGrain)
      ? (rawGrain as OverviewGrain)
      : DEFAULT_OVERVIEW_STATE.grain;

  const rawType = firstValue(query.type);
  const type =
    rawType && TYPE_VALUES.has(rawType as OverviewBadCaseType)
      ? (rawType as OverviewBadCaseType)
      : DEFAULT_OVERVIEW_STATE.type;

  const state: OverviewUrlState = {
    tab: "cases",
    range,
    from: windowFrom,
    to: windowTo,
    grain,
    objects: parseObjects(firstValue(query.objects)),
    page: parsePage(firstValue(query.page)),
    type,
  };

  return {
    state,
    targetsRequested,
    sanitized: !sameOverviewQuery(query, overviewQuery(state)),
  };
}

/**
 * Serialize one overview state into a canonical, human-readable query.
 * @param state Current URL-owned filter state.
 * @returns Query object with only non-default, canonical keys.
 */
export function overviewQuery(state: OverviewUrlState): Record<string, string> {
  const query: Record<string, string> = {
    tab: "cases",
    range: state.range === "custom" ? "custom" : String(state.range),
    grain: state.grain,
  };
  if (state.range === "custom" && state.from && state.to) {
    query.from = state.from;
    query.to = state.to;
  }
  if (state.objects.length > 0) {
    query.objects = state.objects.join(",");
  }
  if (state.type !== "all") {
    query.type = state.type;
  }
  if (state.page > 1) {
    query.page = String(state.page);
  }
  return query;
}

function currentQuery(query: Record<string, unknown>): Record<string, string> {
  const entries: Record<string, string> = {};
  for (const [key, value] of Object.entries(query)) {
    const text = firstValue(value);
    if (text !== null) entries[key] = text;
  }
  return entries;
}

/**
 * Compare the raw route query with a canonical query, ignoring key order.
 * @param current Raw `route.query` object.
 * @param next Canonical query built by `overviewQuery`.
 * @returns True when both carry exactly the same string entries.
 */
export function sameOverviewQuery(
  current: Record<string, unknown>,
  next: Record<string, string>,
): boolean {
  const left = currentQuery(current);
  const leftKeys = Object.keys(left).sort();
  const rightKeys = Object.keys(next).sort();
  return (
    leftKeys.length === rightKeys.length &&
    leftKeys.every(
      (key, index) => key === rightKeys[index] && left[key] === next[key],
    )
  );
}

function isoDate(year: number, month: number, day: number): string {
  return new Date(Date.UTC(year, month - 1, day)).toISOString().slice(0, 10);
}

function lastDayOfMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

/**
 * Resolve the inclusive local window represented by one trend bucket.
 * @param bucket Full ISO bucket start (`YYYY-MM-DD`); week buckets start Monday.
 * @param grain Bucket grain returned by the API.
 * @returns Inclusive from/to dates, or null for an unusable bucket.
 */
export function bucketWindow(
  bucket: string,
  grain: OverviewGrain,
): { from: string; to: string } | null {
  const date = validDate(bucket);
  if (!date) return null;
  const [year, month, day] = date.split("-").map(Number) as [
    number,
    number,
    number,
  ];
  if (grain === "week") {
    const end = new Date(Date.UTC(year, month - 1, day + 6));
    return { from: date, to: end.toISOString().slice(0, 10) };
  }
  if (grain === "month") {
    return {
      from: isoDate(year, month, 1),
      to: isoDate(year, month, lastDayOfMonth(year, month)),
    };
  }
  return { from: date, to: date };
}

/** Server window parameters derived from the URL state. */
export type OverviewWindowFilters = {
  from?: string;
  to?: string;
  range?: OverviewRange;
  objects: string[];
};

/**
 * Convert the URL state into the shared overview API window filters.
 * @param state Current URL-owned filter state.
 * @returns Explicit boundaries for a custom window, otherwise the quick range.
 */
export function overviewWindowFilters(
  state: OverviewUrlState,
): OverviewWindowFilters {
  if (state.range === "custom" && state.from && state.to) {
    return { from: state.from, to: state.to, objects: state.objects };
  }
  return { range: state.range as OverviewRange, objects: state.objects };
}
