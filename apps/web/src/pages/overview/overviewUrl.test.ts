import { describe, expect, it } from "vitest";

import {
  bucketWindow,
  DEFAULT_OVERVIEW_STATE,
  overviewQuery,
  overviewWindowFilters,
  parseOverviewQuery,
  sameOverviewQuery,
} from "./overviewUrl";

describe("overview URL model", () => {
  it("falls back to the 90-day weekly defaults for an empty URL", () => {
    const parsed = parseOverviewQuery({});

    expect(parsed.state).toEqual(DEFAULT_OVERVIEW_STATE);
    expect(parsed.targetsRequested).toBe(false);
    expect(parsed.sanitized).toBe(true);
    expect(overviewQuery(DEFAULT_OVERVIEW_STATE)).toEqual({
      tab: "cases",
      range: "90",
      grain: "week",
    });
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
    expect(parsed.targetsRequested).toBe(true);
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
