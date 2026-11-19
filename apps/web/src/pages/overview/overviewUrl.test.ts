import { describe, expect, it } from "vitest";

import {
  bucketWindow,
  DEFAULT_OVERVIEW_STATE,
  overviewListWindow,
  overviewQuery,
  overviewWindowFilters,
  parseOverviewQuery,
  sameOverviewQuery,
} from "./overviewUrl";

describe("overview URL model", () => {
  it("falls back to the 90-day weekly defaults for an empty URL", () => {
    const parsed = parseOverviewQuery({});

    expect(parsed.state).toEqual(DEFAULT_OVERVIEW_STATE);
    expect(parsed.sanitized).toBe(true);
    expect(overviewQuery(DEFAULT_OVERVIEW_STATE)).toEqual({
      tab: "cases",
      range: "90",
      grain: "week",
    });
  });

  it("defaults a 7-day URL to day grain but keeps an explicit grain", () => {
    const seven = parseOverviewQuery({ range: "7" });

    expect(seven.state.range).toBe(7);
    expect(seven.state.grain).toBe("day");
    expect(overviewQuery(seven.state)).toEqual({
      tab: "cases",
      range: "7",
      grain: "day",
    });
    expect(seven.sanitized).toBe(true);

    const explicitWeek = parseOverviewQuery({ range: "7", grain: "week" });
    expect(explicitWeek.state.grain).toBe("week");
    expect(overviewQuery(explicitWeek.state)).toEqual({
      tab: "cases",
      range: "7",
      grain: "week",
    });

    const thirty = parseOverviewQuery({ range: "30" });
    expect(thirty.state.grain).toBe("week");
  });

  it("restores a fully populated filter URL", () => {
    const parsed = parseOverviewQuery({
      tab: "cases",
      range: "30",
      grain: "day",
      objects: "deep-research,workflow",
      page: "3",
      type: "discovery",
    });

    expect(parsed.state.range).toBe(30);
    expect(parsed.state.grain).toBe("day");
    expect(parsed.state.objects).toEqual(["deep-research", "workflow"]);
    expect(parsed.state.page).toBe(3);
    expect(parsed.state.type).toBe("discovery");
    expect(parsed.sanitized).toBe(false);
  });

  it("round-trips the independent list date, source and type filters", () => {
    const parsed = parseOverviewQuery({
      tab: "cases",
      range: "7",
      grain: "day",
      objects: "deep-research",
      type: "discovery",
      lfrom: "2026-10-01",
      lto: "2026-10-31",
      lobject: " workflow ",
      page: "4",
    });

    expect(parsed.state.listFrom).toBe("2026-10-01");
    expect(parsed.state.listTo).toBe("2026-10-31");
    expect(parsed.state.listObject).toBe("workflow");
    expect(parsed.state.type).toBe("discovery");
    expect(parsed.state.page).toBe(4);
    expect(overviewQuery(parsed.state)).toEqual({
      tab: "cases",
      range: "7",
      grain: "day",
      objects: "deep-research",
      type: "discovery",
      lfrom: "2026-10-01",
      lto: "2026-10-31",
      lobject: "workflow",
      page: "4",
    });
    expect(parsed.sanitized).toBe(true);
    expect(overviewListWindow(parsed.state)).toEqual({
      from: "2026-10-01",
      to: "2026-10-31",
    });
  });

  it("drops an incomplete or inverted list window and keeps the list unlimited", () => {
    const incomplete = parseOverviewQuery({
      lfrom: "2026-10-01",
      lto: "",
    });
    expect(incomplete.state.listFrom).toBe("");
    expect(overviewListWindow(incomplete.state)).toBeNull();
    expect(overviewQuery(incomplete.state)).toEqual({
      tab: "cases",
      range: "90",
      grain: "week",
    });

    const inverted = parseOverviewQuery({
      lfrom: "2026-10-31",
      lto: "2026-10-01",
    });
    expect(inverted.state.listFrom).toBe("");
    expect(inverted.state.listTo).toBe("");
    expect(overviewListWindow(inverted.state)).toBeNull();
  });

  it("keeps legacy page/type keys as the list's page and type", () => {
    const parsed = parseOverviewQuery({ page: "2", type: "self" });

    expect(parsed.state.page).toBe(2);
    expect(parsed.state.type).toBe("self");
    expect(parsed.state.listObject).toBe("");
    expect(overviewQuery(parsed.state)).toEqual({
      tab: "cases",
      range: "90",
      grain: "week",
      type: "self",
      page: "2",
    });
  });

  it("canonicalizes object whitespace and duplicates", () => {
    const spaced = parseOverviewQuery({
      tab: "cases",
      range: "90",
      grain: "week",
      objects: " deep-research , deep-research, workflow ",
    });

    expect(spaced.state.objects).toEqual(["deep-research", "workflow"]);
    expect(overviewQuery(spaced.state).objects).toBe("deep-research,workflow");
    expect(spaced.sanitized).toBe(true);
  });

  it("keeps a custom window only when both boundaries are valid and ordered", () => {
    const custom = parseOverviewQuery({
      range: "custom",
      from: "2026-10-01",
      to: "2026-10-31",
    });
    expect(custom.state.range).toBe("custom");
    expect(custom.state.from).toBe("2026-10-01");
    expect(custom.state.to).toBe("2026-10-31");
    expect(overviewQuery(custom.state)).toEqual({
      tab: "cases",
      range: "custom",
      grain: "week",
      from: "2026-10-01",
      to: "2026-10-31",
    });

    const reversed = parseOverviewQuery({
      range: "custom",
      from: "2026-10-31",
      to: "2026-10-01",
    });
    expect(reversed.state.range).toBe(90);
    expect(reversed.state.from).toBe("");

    const missing = parseOverviewQuery({ range: "custom", from: "2026-10-01" });
    expect(missing.state.range).toBe(90);

    const invalidDate = parseOverviewQuery({
      range: "custom",
      from: "2026-02-31",
      to: "2026-03-01",
    });
    expect(invalidDate.state.range).toBe(90);

    const inferred = parseOverviewQuery({
      from: "2026-10-01",
      to: "2026-10-02",
    });
    expect(inferred.state.range).toBe("custom");
  });

  it("ignores invalid values and foreign query keys", () => {
    const parsed = parseOverviewQuery({
      tab: "targets",
      range: "365",
      grain: "hour",
      page: "-2",
      type: "unknown",
      objects: ",,  ",
      unrelated: "x",
    });

    expect(parsed.state.range).toBe(90);
    expect(parsed.state.grain).toBe("week");
    expect(parsed.state.page).toBe(1);
    expect(parsed.state.type).toBe("all");
    expect(parsed.state.objects).toEqual([]);
    expect(parsed.state.tab).toBe("targets");
    expect(parsed.sanitized).toBe(true);
  });

  it("accepts the first value of a repeated query parameter", () => {
    const parsed = parseOverviewQuery({
      range: ["7", "30"],
      grain: "month",
      page: "2",
    });

    expect(parsed.state.range).toBe(7);
    expect(parsed.state.grain).toBe("month");
    expect(parsed.state.page).toBe(2);
  });

  it("compares canonical queries independent of key order", () => {
    expect(
      sameOverviewQuery(
        { grain: "week", range: "90", tab: "cases" },
        { tab: "cases", range: "90", grain: "week" },
      ),
    ).toBe(true);
    expect(
      sameOverviewQuery(
        { tab: "cases", range: "90", grain: "week", page: "1" },
        { tab: "cases", range: "90", grain: "week" },
      ),
    ).toBe(false);
  });

  it("derives explicit boundaries only for a custom window", () => {
    expect(overviewWindowFilters(DEFAULT_OVERVIEW_STATE)).toEqual({
      range: 90,
      objects: [],
    });
    expect(
      overviewWindowFilters({
        ...DEFAULT_OVERVIEW_STATE,
        range: "custom",
        from: "2026-10-01",
        to: "2026-10-31",
        objects: ["a"],
      }),
    ).toEqual({ from: "2026-10-01", to: "2026-10-31", objects: ["a"] });
  });

  it("round-trips the target view selection and paging", () => {
    const state = {
      ...DEFAULT_OVERVIEW_STATE,
      tab: "targets" as const,
      targets: ["target-a", "target-b"],
      states: ["attributed", "unanalyzed"] as const,
      targetPage: 2,
      caseTarget: "target-a",
      caseSource: "Explore",
      caseState: "nonTarget" as const,
      caseFrom: "2026-10-01",
      caseTo: "2026-10-31",
      page: 3,
      detailTarget: "target-b",
      detailVersions: ["v2", "v1"],
      detailFrom: "2026-11-01",
      detailTo: "2026-11-10",
      detailLimit: "all" as const,
    };
    const query = overviewQuery({ ...state, states: [...state.states] });

    expect(query).toEqual({
      tab: "targets",
      range: "90",
      grain: "week",
      targets: "target-a,target-b",
      states: "attributed,unanalyzed",
      tpage: "2",
      ctarget: "target-a",
      csource: "Explore",
      cstate: "nonTarget",
      cfrom: "2026-10-01",
      cto: "2026-10-31",
      page: "3",
      dtarget: "target-b",
      dversions: "v2,v1",
      dfrom: "2026-11-01",
      dto: "2026-11-10",
      dlimit: "all",
    });
    const parsed = parseOverviewQuery(query);
    expect(parsed.state.tab).toBe("targets");
    expect(parsed.state.targets).toEqual(["target-a", "target-b"]);
    expect(parsed.state.states).toEqual(["attributed", "unanalyzed"]);
    expect(parsed.state.targetPage).toBe(2);
    expect(parsed.state.caseState).toBe("nonTarget");
    expect(parsed.state.detailVersions).toEqual(["v2", "v1"]);
    expect(parsed.state.detailLimit).toBe("all");
    expect(parsed.sanitized).toBe(false);
  });

  it("drops invalid target-view values and keeps case-tab keys out of the target URL", () => {
    const parsed = parseOverviewQuery({
      tab: "targets",
      states: "attributed,bogus",
      dlimit: "7",
      cstate: "unknown",
      cfrom: "2026-10-31",
      cto: "2026-10-01",
      detailTarget: " ",
      dversions: " , v1 , v1 ",
    });

    expect(parsed.state.states).toEqual(["attributed"]);
    expect(parsed.state.detailLimit).toBe(5);
    expect(parsed.state.caseState).toBe("all");
    expect(parsed.state.caseFrom).toBe("");
    expect(parsed.state.caseTo).toBe("");
    expect(parsed.state.detailTarget).toBe("");
    expect(parsed.state.detailVersions).toEqual(["v1"]);
    expect(overviewQuery(parsed.state)).toEqual({
      tab: "targets",
      range: "90",
      grain: "week",
      states: "attributed",
      dversions: "v1",
    });
    expect(overviewQuery({ ...parsed.state, tab: "cases" })).toEqual({
      tab: "cases",
      range: "90",
      grain: "week",
    });
  });

  it("turns a clicked bucket into an inclusive window", () => {
    expect(bucketWindow("2026-10-20", "day")).toEqual({
      from: "2026-10-20",
      to: "2026-10-20",
    });
    expect(bucketWindow("2026-10-19", "week")).toEqual({
      from: "2026-10-19",
      to: "2026-10-25",
    });
    expect(bucketWindow("2026-11-01", "month")).toEqual({
      from: "2026-11-01",
      to: "2026-11-30",
    });
    expect(bucketWindow("2026-02-01", "month")).toEqual({
      from: "2026-02-01",
      to: "2026-02-28",
    });
    expect(bucketWindow("not-a-date", "day")).toBeNull();
    expect(bucketWindow("", "week")).toBeNull();
  });
});
