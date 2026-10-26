/** Presentation tab accepted by the formal Session error route. */
export type DeepLinkTab = "desc" | "attr";

/** Canonical Session deep-link state derived only from the URL. */
export interface SessionDeepLinkState {
  sessionId: string;
  agentId: string | null;
  eventIndex: number | null;
  badCaseId: string | null;
  tab: DeepLinkTab;
}

type DeepLinkQuery = Record<string, unknown>;
/** Route surface that owns the query contract. */
export type DeepLinkSurface = "session" | "error";

/** Canonical parsed Session deep state or a stable validation failure. */
export type SessionDeepLinkParseResult =
  | {
      ok: true;
      state: SessionDeepLinkState;
      canonicalQuery: Record<string, string>;
    }
  | {
      ok: false;
      code: "DEEP_LINK_INVALID";
      field: string;
      message: string;
    };

/** Result of checking bad-case ownership against a Session route. */
export type BadCaseSessionResolution =
  | {
      ok: true;
      badCaseId: string;
      sessionId: string;
    }
  | {
      ok: false;
      status: 409;
      code: "BAD_CASE_SESSION_MISMATCH";
      message: string;
    };

const SESSION_ID_MAX = 36;
const AGENT_ID_MAX = 64;
const BAD_CASE_ID_MAX = 64;
const SAFE_ID = /^[A-Za-z0-9_.:@-]+$/;

function hasControlCharacter(value: string): boolean {
  for (const character of value) {
    const codePoint = character.codePointAt(0) ?? 0;
    if (codePoint <= 31 || codePoint === 127) {
      return true;
    }
  }
  return false;
}

function invalid(field: string, message: string): SessionDeepLinkParseResult {
  return {
    ok: false,
    code: "DEEP_LINK_INVALID",
    field,
    message,
  };
}

function queryString(
  query: DeepLinkQuery,
  key: string,
): { ok: true; value: string | null } | { ok: false } {
  const value = query[key];
  if (value === undefined || value === null) {
    return { ok: true, value: null };
  }
  return typeof value === "string"
    ? { ok: true, value }
    : { ok: false };
}

function validateSessionId(value: string): string | null {
  if (
    !value ||
    value.length > SESSION_ID_MAX ||
    hasControlCharacter(value) ||
    !SAFE_ID.test(value)
  ) {
    return null;
  }
  return value;
}

function validQueryId(
  value: string | null,
  maxLength: number,
): value is string {
  return Boolean(
    value &&
      value.trim() === value &&
      value.length <= maxLength &&
      !hasControlCharacter(value) &&
      SAFE_ID.test(value),
  );
}

/**
 * Parse and canonicalize Session deep-link state.
 * @param rawSessionId Session id taken from the already-decoded Vue Router path segment.
 * @param query Router query values.
 * @param surface Route surface that owns the query contract.
 * @returns Canonical state or a stable validation error.
 */
export function parseSessionDeepLink(
  rawSessionId: string,
  query: DeepLinkQuery,
  surface: DeepLinkSurface = "session",
): SessionDeepLinkParseResult {
  const sessionId = validateSessionId(rawSessionId);
  if (!sessionId) {
    return invalid("sessionId", "Session 深链无效");
  }

  const agent = queryString(query, "agent");
  if (!agent.ok || (agent.value !== null && !validQueryId(agent.value, AGENT_ID_MAX))) {
    return invalid("agent", "链接中的 Agent 无效");
  }

  const evidenceValue = queryString(query, "evidence");
  if (!evidenceValue.ok) {
    return invalid("evidence", "链接中的证据位置无效");
  }
  let eventIndex: number | null = null;
  if (evidenceValue.value !== null) {
    if (!/^\d+$/.test(evidenceValue.value)) {
      return invalid("evidence", "链接中的证据位置无效");
    }
    eventIndex = Number(evidenceValue.value);
    if (!Number.isSafeInteger(eventIndex)) {
      return invalid("evidence", "链接中的证据位置无效");
    }
  }
  if (eventIndex !== null && agent.value === null) {
    return invalid("evidence", "证据位置必须同时指定 Agent");
  }

  let caseValue: { ok: true; value: string | null } | { ok: false } = {
    ok: true,
    value: null,
  };
  let tabValue: { ok: true; value: string | null } | { ok: false } = {
    ok: true,
    value: null,
  };
  if (surface === "error") {
    caseValue = queryString(query, "case");
    if (
      !caseValue.ok ||
      (caseValue.value !== null &&
        !validQueryId(caseValue.value, BAD_CASE_ID_MAX))
    ) {
      return invalid("case", "链接中的问题无效");
    }

    tabValue = queryString(query, "tab");
    if (!tabValue.ok) {
      return invalid("tab", "链接中的详情页签无效");
    }
  }
  const tab: DeepLinkTab =
    caseValue.value !== null && tabValue.value === "attr" ? "attr" : "desc";

  const canonicalQuery: Record<string, string> = {};
  if (agent.value !== null) {
    canonicalQuery.agent = agent.value;
  }
  if (eventIndex !== null) {
    canonicalQuery.evidence = String(eventIndex);
  }
  if (caseValue.value !== null) {
    canonicalQuery.case = caseValue.value;
    if (tab === "attr") {
      canonicalQuery.tab = "attr";
    }
  }

  return {
    ok: true,
    state: {
      sessionId,
      agentId: agent.value,
      eventIndex,
      badCaseId: caseValue.value,
      tab,
    },
    canonicalQuery,
  };
}

/**
 * Resolve whether a bad-case response belongs to the Session in the URL.
 * @param sessionId Session id from the deep-link path.
 * @param badCase Minimal bad-case ownership response.
 * @returns Success or the formal cross-session mismatch.
 */
export function resolveBadCaseSession(
  sessionId: string,
  badCase: { badCaseId: string; sessionId: string },
): BadCaseSessionResolution {
  if (badCase.sessionId !== sessionId) {
    return {
      ok: false,
      status: 409,
      code: "BAD_CASE_SESSION_MISMATCH",
      message: "问题不属于当前 Session",
    };
  }
  return {
    ok: true,
    badCaseId: badCase.badCaseId,
    sessionId,
  };
}
