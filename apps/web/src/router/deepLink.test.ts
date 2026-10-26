import { describe, expect, it } from "vitest";

import {
  parseSessionDeepLink,
  resolveBadCaseSession,
} from "./deepLink";

describe("session deep links", () => {
  it("parses canonical agent and evidence state", () => {
    expect(
      parseSessionDeepLink("root-1", {
        agent: "agent-1",
        evidence: "2",
      }),
    ).toEqual({
      ok: true,
      state: {
        sessionId: "root-1",
        agentId: "agent-1",
        eventIndex: 2,
        badCaseId: null,
        tab: "desc",
      },
      canonicalQuery: {
        agent: "agent-1",
        evidence: "2",
      },
    });
  });

  it("accepts agent-only, zero, and the largest valid evidence index", () => {
    expect(
      parseSessionDeepLink("root-1", { agent: "agent-1" }),
    ).toMatchObject({
      ok: true,
      state: { agentId: "agent-1", eventIndex: null },
      canonicalQuery: { agent: "agent-1" },
    });
    expect(
      parseSessionDeepLink("root-1", {
        agent: "agent-1",
        evidence: "0",
      }),
    ).toMatchObject({
      ok: true,
      state: { eventIndex: 0 },
    });
    expect(
      parseSessionDeepLink("root-1", {
        agent: "agent-1",
        evidence: "999999",
      }),
    ).toMatchObject({
      ok: true,
      state: { eventIndex: 999999 },
    });
  });

  it.each([
    [{ evidence: "0" }, "evidence"],
    [{ agent: "" }, "agent"],
    [{ agent: "agent-1", evidence: "-1" }, "evidence"],
    [{ agent: "agent-1", evidence: "1.5" }, "evidence"],
    [{ agent: ["a", "b"] }, "agent"],
    [{ agent: "\u0000bad" }, "agent"],
  ])("rejects invalid session deep-link query %#", (query, field) => {
    expect(parseSessionDeepLink("root-1", query)).toMatchObject({
      ok: false,
      code: "DEEP_LINK_INVALID",
      field,
    });
  });

  it("rejects invalid session ids without falling back", () => {
    expect(parseSessionDeepLink("", {})).toMatchObject({
      ok: false,
      code: "DEEP_LINK_INVALID",
      field: "sessionId",
    });
    expect(parseSessionDeepLink("x".repeat(37), {})).toMatchObject({
      ok: false,
      code: "DEEP_LINK_INVALID",
      field: "sessionId",
    });
    expect(parseSessionDeepLink("%00", {})).toMatchObject({
      ok: false,
      code: "DEEP_LINK_INVALID",
      field: "sessionId",
    });
  });

  it("parses formal error route case and tab state", () => {
    expect(
      parseSessionDeepLink(
        "root-1",
        {
          case: "case-1",
          tab: "attr",
        },
        "error",
      ),
    ).toMatchObject({
      ok: true,
      state: {
        badCaseId: "case-1",
        tab: "attr",
      },
      canonicalQuery: {
        case: "case-1",
        tab: "attr",
      },
    });
  });

  it("defaults an unknown tab to description and drops tab without case", () => {
    expect(
      parseSessionDeepLink(
        "root-1",
        {
          case: "case-1",
          tab: "unknown",
        },
        "error",
      ),
    ).toMatchObject({
      ok: true,
      state: { badCaseId: "case-1", tab: "desc" },
      canonicalQuery: { case: "case-1" },
    });
    expect(
      parseSessionDeepLink("root-1", { tab: "attr" }, "error"),
    ).toMatchObject({
      ok: true,
      state: { badCaseId: null, tab: "desc" },
      canonicalQuery: {},
    });
  });

  it.each([
    [{ case: "" }, "case"],
    [{ case: ["a", "b"] }, "case"],
    [{ case: "case-1", tab: ["desc", "attr"] }, "tab"],
    [{ case: "\u001fbad" }, "case"],
  ])("rejects invalid error deep link %#", (query, field) => {
    expect(parseSessionDeepLink("root-1", query, "error")).toMatchObject({
      ok: false,
      code: "DEEP_LINK_INVALID",
      field,
    });
  });

  it("strips error-only query values from a normal Session deep link", () => {
    expect(
      parseSessionDeepLink("root-1", {
        agent: "agent-1",
        case: "case-1",
        tab: "attr",
      }),
    ).toMatchObject({
      ok: true,
      state: {
        badCaseId: null,
        tab: "desc",
      },
      canonicalQuery: { agent: "agent-1" },
    });
  });

  it("does not decode an already-decoded path parameter a second time", () => {
    expect(parseSessionDeepLink("a%41b", {})).toMatchObject({
      ok: false,
      field: "sessionId",
    });
  });
});

describe("bad-case deep-link resolver seam", () => {
  it("accepts a bad case owned by the selected session", () => {
    expect(
      resolveBadCaseSession("root-1", {
        badCaseId: "case-1",
        sessionId: "root-1",
      }),
    ).toEqual({
      ok: true,
      badCaseId: "case-1",
      sessionId: "root-1",
    });
  });

  it("returns a stable mismatch error for a cross-session bad case", () => {
    expect(
      resolveBadCaseSession("root-1", {
        badCaseId: "case-1",
        sessionId: "root-2",
      }),
    ).toEqual({
      ok: false,
      status: 409,
      code: "BAD_CASE_SESSION_MISMATCH",
      message: "问题不属于当前 Session",
    });
  });
});
