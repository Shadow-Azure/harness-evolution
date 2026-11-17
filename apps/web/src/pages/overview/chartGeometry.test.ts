import { describe, expect, it } from "vitest";

import { barLayout, niceTicks, percent, stackSegments, stackY } from "./chartGeometry";

describe("overview chart geometry", () => {
  it("gives an empty or all-zero series a usable 0..1 axis", () => {
    expect(niceTicks(0)).toEqual([0, 1]);
    expect(niceTicks(-4)).toEqual([0, 1]);
    expect(niceTicks(Number.NaN)).toEqual([0, 1]);
  });

  it("uses 1/2/5×10ⁿ steps and always covers the maximum", () => {
    const ticks = niceTicks(11, 4);
    expect(ticks[0]).toBe(0);
    expect(ticks.at(-1)).toBeGreaterThanOrEqual(11);
    expect(ticks.length).toBeGreaterThanOrEqual(2);
    for (let index = 1; index < ticks.length; index += 1) {
      expect(ticks[index]).toBeGreaterThan(ticks[index - 1] as number);
    }
    expect(ticks).toEqual([0, 5, 10, 15]);

    const large = niceTicks(1_234_567, 4);
    expect(large.at(-1)).toBeGreaterThanOrEqual(1_234_567);
    expect(large.at(-1)).toBeLessThan(2_000_000);
    expect(large.every((tick) => Number.isInteger(tick))).toBe(true);
  });

  it("keeps tick arithmetic free of floating point noise", () => {
    const ticks = niceTicks(0.9, 3, 0);
    expect(ticks.every((tick) => String(tick).length <= 6)).toBe(true);
    expect(ticks.at(-1)).toBeGreaterThanOrEqual(0.9);
    expect(new Set(ticks).size).toBe(ticks.length);
  });

  it("lays out a single bucket with the bar width cap", () => {
    expect(barLayout(1, 600)).toEqual({ slot: 600, barWidth: 28, dense: false });
    expect(barLayout(0, 600)).toEqual({ slot: 0, barWidth: 0, dense: false });
    expect(barLayout(3, 0)).toEqual({ slot: 0, barWidth: 0, dense: false });
  });

  it("enters dense mode only beyond sixty buckets", () => {
    expect(barLayout(26, 720).dense).toBe(false);
    expect(barLayout(60, 720).dense).toBe(false);

    const layout = barLayout(61, 720);
    expect(layout.dense).toBe(true);
    expect(layout.slot).toBeCloseTo(720 / 61);
    expect(layout.barWidth).toBeCloseTo((720 / 61) * 0.6);
    expect(layout.barWidth).toBeLessThanOrEqual(28);
  });

  it("stacks self below discovery and clamps to the axis maximum", () => {
    const geometry = stackY(3, 2, 10, 200, 5);
    expect(geometry.y).toBe(10);
    expect(geometry.totalHeight).toBe(200);
    expect(geometry.selfHeight).toBeCloseTo(120);
    expect(geometry.discoveryHeight).toBeCloseTo(80);
    expect(geometry.selfHeight + geometry.discoveryHeight).toBeCloseTo(
      geometry.totalHeight,
    );

    const clamped = stackY(10, 10, 10, 100, 5);
    expect(clamped.totalHeight).toBe(100);

    const zero = stackY(0, 0, 10, 100, 5);
    expect(zero).toEqual({
      y: 110,
      totalHeight: 0,
      selfHeight: 0,
      discoveryHeight: 0,
    });
  });

  it("draws a visible minimum for a single small bucket", () => {
    const geometry = stackY(1, 0, 0, 200, 10_000);
    expect(geometry.totalHeight).toBe(3);
    expect(geometry.selfHeight).toBe(3);
    expect(geometry.discoveryHeight).toBe(0);
  });

  it("computes bucket shares that sum to one hundred", () => {
    expect(percent(3, 1)).toEqual({ self: 75, discovery: 25 });
    expect(percent(0, 0)).toEqual({ self: 0, discovery: 0 });
    const share = percent(2, 5);
    expect(share.self + share.discovery).toBeCloseTo(100);
  });

  it("stacks an arbitrary number of segments from the baseline", () => {
    const geometry = stackSegments([1, 2, 1], 0, 200, 4);
    expect(geometry.y).toBe(0);
    expect(geometry.totalHeight).toBe(200);
    expect(geometry.heights).toEqual([50, 100, 50]);
    expect(geometry.heights.reduce((sum, value) => sum + value, 0)).toBeCloseTo(
      geometry.totalHeight,
    );

    const clamped = stackSegments([10, 0, 10], 10, 100, 5);
    expect(clamped.totalHeight).toBe(100);
    expect(clamped.heights[1]).toBe(0);

    const zero = stackSegments([0, 0, 0], 10, 100, 5);
    expect(zero).toEqual({ y: 110, totalHeight: 0, heights: [0, 0, 0] });
  });
});
