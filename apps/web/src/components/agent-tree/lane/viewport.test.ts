import { describe, expect, it } from "vitest";

import {
  centerOn,
  clampZoom,
  fitViewport,
  pan,
  resetViewport,
  zoomAt,
} from "./viewport";

describe("lane viewport", () => {
  it("clamps zoom into the supported 0.08–3 range", () => {
    expect(clampZoom(0.01)).toBe(0.08);
    expect(clampZoom(10)).toBe(3);
    expect(clampZoom(Number.NaN)).toBe(1);
  });

  it("keeps the pointer position fixed while zooming", () => {
    const view = { x: 40, y: 30, k: 1 };
    const next = zoomAt(view, 2, 120, 80);
    expect(next.k).toBe(2);
    expect((120 - next.x) / next.k).toBeCloseTo(120 - view.x);
    expect((80 - next.y) / next.k).toBeCloseTo(80 - view.y);
  });

  it("pans by pointer delta without changing zoom", () => {
    expect(pan({ x: 1, y: 2, k: 0.5 }, 10, -5)).toEqual({ x: 11, y: -3, k: 0.5 });
  });

  it("fits and centers a large canvas inside the small viewport", () => {
    const view = fitViewport(1100, 2580, 900, 400);
    expect(view.k).toBeGreaterThanOrEqual(0.08);
    expect(view.k).toBeLessThan(0.2);
    expect(view.x).toBeGreaterThanOrEqual(0);
    expect(view.y).toBeGreaterThanOrEqual(0);
    expect(1100 * view.k + view.x).toBeCloseTo(900 - view.x);
    expect(2580 * view.k + view.y).toBeCloseTo(400 - view.y);
  });

  it("centers a content point and raises zoom for locating", () => {
    const view = centerOn({ x: 0, y: 0, k: 0.1 }, 500, 100, 900, 400, 0.6);
    expect(view.k).toBe(0.6);
    expect(500 * view.k + view.x).toBeCloseTo(450);
    expect(100 * view.k + view.y).toBeCloseTo(200);
  });

  it("resets to the identity transform", () => {
    expect(resetViewport()).toEqual({ x: 0, y: 0, k: 1 });
  });
});
