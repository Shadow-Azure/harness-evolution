import type {
  OverviewBadCaseType,
  OverviewGrain,
  OverviewRange,
  TargetState,
} from "@harness/contracts";

/** Quick range choices plus the custom window the filter bar can open. */
export type OverviewRangeChoice = OverviewRange | "custom";

/** The two views the overview page switches between. */
export type OverviewTab = "cases" | "targets";

/** Detail-card version window; `all` maps to the API's `versionLimit=0`. */
export type DetailVersionLimit = 5 | 10 | 20 | "all";

/** Everything the overview URL owns; the page derives its queries from it. */
export type OverviewUrlState = {
  tab: OverviewTab;
  range: OverviewRangeChoice;
  from: string;
  to: string;
  grain: OverviewGrain;
  objects: string[];
  page: number;
  type: OverviewBadCaseType;
  /** Bad-case list's independent start date; paired with `listTo`. */
  listFrom: string;
  /** Bad-case list's independent end date; paired with `listFrom`. */
  listTo: string;
  /** Bad-case list's independent reported-source filter; empty means every source. */
  listObject: string;
  /** Selected evolution target ids driving the target trend and distributions. */
  targets: string[];
  /** Selected target states driving the trend; empty means all three. */
  states: TargetState[];
  /** 1-based page of the evolution-target side list. */
  targetPage: number;
  /** Potential-case list's own target filter; empty means every selected target. */
  caseTarget: string;
  /** Potential-case list's own reported-source filter. */
  caseSource: string;
  /** Potential-case list's own attribution-state filter. */
  caseState: TargetState | "all";
  /** Potential-case list's independent start date; used with `caseTo`. */
  caseFrom: string;
  /** Potential-case list's independent end date; used with `caseFrom`. */
  caseTo: string;
  /** Target shown by the independent single-target analysis card. */
  detailTarget: string;
  /** Explicit versions of the analysis card; empty uses `detailLimit`. */
  detailVersions: string[];
  /** Analysis card's independent start date; used with `detailTo`. */
  detailFrom: string;
  /** Analysis card's independent end date; used with `detailFrom`. */
  detailTo: string;
  /** Newest-version window of the analysis card when no version is explicit. */
  detailLimit: DetailVersionLimit;
};

/** Result of parsing one raw route query. */
export type OverviewParsedQuery = {
  state: OverviewUrlState;
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
  listFrom: "",
  listTo: "",
  listObject: "",
  targets: [],
  states: [],
  targetPage: 1,
  caseTarget: "",
  caseSource: "",
  caseState: "all",
  caseFrom: "",
  caseTo: "",
  detailTarget: "",
  detailVersions: [],
  detailFrom: "",
  detailTo: "",
  detailLimit: 5,
};

const RANGE_VALUES = new Set([7, 30, 90]);
const GRAIN_VALUES = new Set<OverviewGrain>(["day", "week", "month"]);
const TYPE_VALUES = new Set<OverviewBadCaseType>(["all", "self", "discovery"]);
const STATE_VALUES = new Set<TargetState>([
  "attributed",
  "nonTarget",
  "unanalyzed",
]);
const VERSION_LIMITS = new Set<DetailVersionLimit>([5, 10, 20, "all"]);
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

function parseList(value: string | null): string[] {
  if (!value) return [];
  const seen = new Set<string>();
  for (const raw of value.split(",")) {
    const name = raw.trim();
    if (name) seen.add(name);
  }
  return [...seen];
}

function validWindow(
  from: string,
  to: string,
): { from: string; to: string } | null {
  return from && to && from <= to ? { from, to } : null;
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

function parseStates(value: string | null): TargetState[] {
  return parseList(value).filter((state): state is TargetState =>
    STATE_VALUES.has(state as TargetState),
  );
}

function parseCaseState(value: string | null): TargetState | "all" {
  return value && STATE_VALUES.has(value as TargetState)
    ? (value as TargetState)
    : "all";
}

function parseDetailLimit(value: string | null): DetailVersionLimit {
  if (value === "all") return "all";
  const numeric = value === null ? null : Number(value);
  return numeric !== null && VERSION_LIMITS.has(numeric as DetailVersionLimit)
    ? (numeric as DetailVersionLimit)
    : DEFAULT_OVERVIEW_STATE.detailLimit;
}

/**
 * Normalize one raw route query into the canonical overview state.
 * @param query Raw `route.query` object.
 * @returns The parsed state plus the sanitization flag the page needs.
 */
export function parseOverviewQuery(
  query: Record<string, unknown>,
): OverviewParsedQuery {
  const tab: OverviewTab =
    firstValue(query.tab) === "targets" ? "targets" : "cases";

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
      : range === 7
        ? "day"
        : DEFAULT_OVERVIEW_STATE.grain;

  const rawType = firstValue(query.type);
  const type =
    rawType && TYPE_VALUES.has(rawType as OverviewBadCaseType)
      ? (rawType as OverviewBadCaseType)
      : DEFAULT_OVERVIEW_STATE.type;

  const caseWindow = validWindow(
    validDate(firstValue(query.cfrom)),
    validDate(firstValue(query.cto)),
  );
  const detailWindow = validWindow(
    validDate(firstValue(query.dfrom)),
    validDate(firstValue(query.dto)),
  );
  // The list owns its dates: an incomplete or inverted pair is dropped rather
  // than silently narrowed to the chart's window, so an old URL cannot make the
  // list look filtered when it is not.
  const listWindow = validWindow(
    validDate(firstValue(query.lfrom)),
    validDate(firstValue(query.lto)),
  );

  const state: OverviewUrlState = {
    tab,
    range,
    from: windowFrom,
    to: windowTo,
    grain,
    objects: parseList(firstValue(query.objects)),
    page: parsePage(firstValue(query.page)),
    type,
    listFrom: listWindow?.from ?? "",
    listTo: listWindow?.to ?? "",
    listObject: firstValue(query.lobject)?.trim() ?? "",
    targets: parseList(firstValue(query.targets)),
    states: parseStates(firstValue(query.states)),
    targetPage: parsePage(firstValue(query.tpage)),
    caseTarget: firstValue(query.ctarget)?.trim() ?? "",
    caseSource: firstValue(query.csource)?.trim() ?? "",
    caseState: parseCaseState(firstValue(query.cstate)),
    caseFrom: caseWindow?.from ?? "",
    caseTo: caseWindow?.to ?? "",
    detailTarget: firstValue(query.dtarget)?.trim() ?? "",
    detailVersions: parseList(firstValue(query.dversions)),
    detailFrom: detailWindow?.from ?? "",
    detailTo: detailWindow?.to ?? "",
    detailLimit: parseDetailLimit(firstValue(query.dlimit)),
  };

  return {
    state,
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
    tab: state.tab,
    range: state.range === "custom" ? "custom" : String(state.range),
    grain: state.grain,
  };
  if (state.range === "custom" && state.from && state.to) {
    query.from = state.from;
    query.to = state.to;
  }
  if (state.tab === "cases") {
    if (state.objects.length > 0) {
      query.objects = state.objects.join(",");
    }
    if (state.type !== "all") {
      query.type = state.type;
    }
    if (state.listFrom && state.listTo) {
      query.lfrom = state.listFrom;
      query.lto = state.listTo;
    }
    if (state.listObject) {
      query.lobject = state.listObject;
    }
    if (state.page > 1) {
      query.page = String(state.page);
    }
    return query;
  }
  if (state.targets.length > 0) {
    query.targets = state.targets.join(",");
  }
  if (state.states.length > 0) {
    query.states = state.states.join(",");
  }
  if (state.targetPage > 1) {
    query.tpage = String(state.targetPage);
  }
  if (state.caseTarget) {
    query.ctarget = state.caseTarget;
  }
  if (state.caseSource) {
    query.csource = state.caseSource;
  }
  if (state.caseState !== "all") {
    query.cstate = state.caseState;
  }
  if (state.caseFrom && state.caseTo) {
    query.cfrom = state.caseFrom;
    query.cto = state.caseTo;
  }
  if (state.page > 1) {
    query.page = String(state.page);
  }
  if (state.detailTarget) {
    query.dtarget = state.detailTarget;
  }
  if (state.detailVersions.length > 0) {
    query.dversions = state.detailVersions.join(",");
  }
  if (state.detailFrom && state.detailTo) {
    query.dfrom = state.detailFrom;
    query.dto = state.detailTo;
  }
  if (state.detailLimit !== DEFAULT_OVERVIEW_STATE.detailLimit) {
    query.dlimit = String(state.detailLimit);
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

/**
 * Resolve the shared window without the case-tab object filter.
 * @param state Current URL-owned filter state.
 * @returns Explicit boundaries for a custom window, otherwise the quick range.
 */
export function overviewSharedWindow(state: OverviewUrlState): {
  from?: string;
  to?: string;
  range?: OverviewRange;
} {
  if (state.range === "custom" && state.from && state.to) {
    return { from: state.from, to: state.to };
  }
  return { range: state.range as OverviewRange };
}

/**
 * Resolve the potential-case list's own window, falling back to the shared one.
 * @param state Current URL-owned filter state.
 * @returns Explicit list boundaries when both are set, otherwise the shared window.
 */
export function overviewCaseWindow(state: OverviewUrlState): {
  from?: string;
  to?: string;
  range?: OverviewRange;
} {
  if (state.caseFrom && state.caseTo) {
    return { from: state.caseFrom, to: state.caseTo };
  }
  return overviewSharedWindow(state);
}

/**
 * Resolve the bad-case list's own window without inheriting the chart's one.
 * @param state Current URL-owned filter state.
 * @returns Both list boundaries when set, otherwise null meaning "all time".
 */
export function overviewListWindow(state: OverviewUrlState): {
  from: string;
  to: string;
} | null {
  return state.listFrom && state.listTo
    ? { from: state.listFrom, to: state.listTo }
    : null;
}

/**
 * Resolve the analysis card's independent window, falling back to the shared one.
 * @param state Current URL-owned filter state.
 * @returns Explicit card boundaries when both are set, otherwise the shared window.
 */
export function overviewDetailWindow(state: OverviewUrlState): {
  from?: string;
  to?: string;
  range?: OverviewRange;
} {
  if (state.detailFrom && state.detailTo) {
    return { from: state.detailFrom, to: state.detailTo };
  }
  return overviewSharedWindow(state);
}
