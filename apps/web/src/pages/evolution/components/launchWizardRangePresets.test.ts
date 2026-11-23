import { describe, expect, it } from "vitest";

import {
  activePresetId,
  addCalendarDays,
  addCalendarMonths,
  localIsoDate,
  presetRange,
} from "./launchWizardRangePresets";

describe("launch wizard range presets", () => {
  it("formats a local calendar day without a UTC shift", () => {
    expect(localIsoDate(new Date(2026, 10, 10, 12, 0, 0))).toBe("2026-11-10");
    expect(localIsoDate(new Date(2026, 0, 1, 0, 30, 0))).toBe("2026-01-01");
  });

  it("adds calendar days across month and year boundaries", () => {
    expect(addCalendarDays("2026-11-10", -6)).toBe("2026-11-04");
    expect(addCalendarDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(addCalendarDays("2026-03-01", -1)).toBe("2026-02-28");
  });

  it("clamps calendar months to the target month's last day", () => {
    expect(addCalendarMonths("2026-11-10", -6)).toBe("2026-05-10");
    expect(addCalendarMonths("2026-08-31", -6)).toBe("2026-02-28");
    expect(addCalendarMonths("2024-08-31", -6)).toBe("2024-02-29");
    expect(addCalendarMonths("2026-03-31", -1)).toBe("2026-02-28");
  });

  it("computes the three closed preset ranges from the demo day", () => {
    expect(presetRange("7", "2026-11-10")).toEqual({
      from: "2026-11-04",
      to: "2026-11-10",
    });
    expect(presetRange("30", "2026-11-10")).toEqual({
      from: "2026-10-12",
      to: "2026-11-10",
    });
    expect(presetRange("6m", "2026-11-10")).toEqual({
      from: "2026-05-10",
      to: "2026-11-10",
    });
  });

  it("matches only the exact active range and treats custom values as none", () => {
    expect(activePresetId("2026-11-04", "2026-11-10", "2026-11-10")).toBe("7");
    expect(activePresetId("2026-10-12", "2026-11-10", "2026-11-10")).toBe("30");
    expect(activePresetId("2026-05-10", "2026-11-10", "2026-11-10")).toBe("6m");
    expect(activePresetId("2026-05-10", "2026-11-09", "2026-11-10")).toBeNull();
    expect(activePresetId("", "", "2026-11-10")).toBeNull();
  });

  it("rejects values that are not real calendar days", () => {
    expect(() => addCalendarDays("2026-02-30", 1)).toThrow(
      "invalid calendar day: 2026-02-30",
    );
    expect(() => addCalendarMonths("10/11/2026", -6)).toThrow(
      "invalid calendar day: 10/11/2026",
    );
  });
});
