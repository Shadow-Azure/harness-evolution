/**
 * Pure geometry for the overview SVG stacked trend.
 *
 * The chart never imports a drawing library: buckets become bar heights in
 * pixels, the y axis uses 1/2/5×10ⁿ ticks, and the same helpers are unit-tested
 * for empty, all-zero, single-bucket, and dense (>60 buckets) inputs.
 */

/** Horizontal slot and bar width of one bucket column. */
export type BarLayout = {
  /** Width reserved for one bucket, including its gap. */
  slot: number;
  /** Drawn bar width; at most 28px and 60% of the slot. */
  barWidth: number;
  /** Whether the bucket count needs the compact label/gap policy. */
  dense: boolean;
};

/** Vertical geometry of one stacked bucket bar. */
export type StackGeometry = {
  /** Top edge of the bar in local chart pixels. */
  y: number;
  /** Total bar height including both segments. */
  totalHeight: number;
  /** Bottom self segment height. */
  selfHeight: number;
  /** Top discovery segment height. */
  discoveryHeight: number;
};

/** Self/discovery share of one bucket, in percent. */
export type BucketShare = {
  self: number;
  discovery: number;
};

const DEFAULT_TICK_COUNT = 4;
const MAX_BAR_WIDTH = 28;
const BAR_SLOT_RATIO = 0.6;
const DENSE_BUCKET_COUNT = 26;
const MIN_BAR_HEIGHT = 3;

function decimalsFor(step: number): number {
  if (!Number.isFinite(step) || step <= 0) return 0;
  const text = String(step);
  const exponent = text.includes("e")
    ? Number(text.split("e")[1] ?? 0)
    : 0;
  if (exponent < 0) return Math.min(12, -exponent);
  const dot = text.indexOf(".");
  return dot === -1 ? 0 : text.length - dot - 1;
}

function round(value: number, decimals: number): number {
  const factor = 10 ** decimals;
  return Math.round(value * factor) / factor;
}

function niceStep(rawStep: number, minStep: number): number {
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const residual = rawStep / magnitude;
  const scaled = residual <= 1 ? 1 : residual <= 2 ? 2 : residual <= 5 ? 5 : 10;
  return Math.max(minStep, scaled * magnitude);
}

/**
 * Build ascending axis ticks covering `max` with at most about `count` intervals.
 * @param max Largest value that must fit on the axis; non-positive values use 1.
 * @param count Preferred number of intervals.
 * @param minStep Smallest step allowed; defaults to 1 so counters stay integral.
 * @returns Ascending ticks from 0 to the first tick at or above `max`.
 */
export function niceTicks(
  max: number,
  count = DEFAULT_TICK_COUNT,
  minStep = 1,
): number[] {
  const safeCount = Number.isFinite(count) ? Math.max(1, Math.floor(count)) : DEFAULT_TICK_COUNT;
  const target = Number.isFinite(max) && max > 0 ? max : 1;
  const step = niceStep(target / safeCount, minStep);
  const decimals = decimalsFor(step);
  const ticks = [0];
  let value = 0;
  const guard = safeCount * 20 + 20;
  for (let index = 0; index < guard; index += 1) {
    value += step;
    ticks.push(round(value, decimals));
    if (value >= target) break;
  }
  return ticks;
}

/**
 * Lay out bucket columns across a chart width.
 * @param count Number of buckets; non-positive values produce an empty layout.
 * @param width Available chart width in pixels.
 * @returns Slot width, bar width, and density flag.
 */
export function barLayout(count: number, width: number): BarLayout {
  if (!Number.isFinite(count) || count <= 0 || !Number.isFinite(width) || width <= 0) {
    return { slot: 0, barWidth: 0, dense: false };
  }
  const slot = width / count;
  return {
    slot,
    barWidth: Math.min(MAX_BAR_WIDTH, slot * BAR_SLOT_RATIO),
    dense: count > DENSE_BUCKET_COUNT,
  };
}

/**
 * Stack a self/discovery bar from the chart baseline.
 * @param self Self segment value.
 * @param discovery Discovery segment value.
 * @param top Chart drawing top in pixels.
 * @param height Chart drawing height in pixels.
 * @param max Axis maximum; bars are clamped to it.
 * @returns Bar y, total height, and both segment heights.
 */
export function stackY(
  self: number,
  discovery: number,
  top: number,
  height: number,
  max: number,
): StackGeometry {
  const safeSelf = Number.isFinite(self) && self > 0 ? self : 0;
  const safeDiscovery = Number.isFinite(discovery) && discovery > 0 ? discovery : 0;
  const total = safeSelf + safeDiscovery;
  if (total <= 0 || !Number.isFinite(height) || height <= 0 || !Number.isFinite(max) || max <= 0) {
    return {
      y: top + (Number.isFinite(height) ? Math.max(0, height) : 0),
      totalHeight: 0,
      selfHeight: 0,
      discoveryHeight: 0,
    };
  }
  const scaled = Math.min(height, (total / max) * height);
  const totalHeight = Math.max(MIN_BAR_HEIGHT, scaled);
  const selfHeight = (totalHeight * safeSelf) / total;
  return {
    y: top + height - totalHeight,
    totalHeight,
    selfHeight,
    discoveryHeight: totalHeight - selfHeight,
  };
}

/**
 * Split one bucket into percentage shares for tooltips and legends.
 * @param self Self segment value.
 * @param discovery Discovery segment value.
 * @returns Percentages that sum to 100, or both zero for an empty bucket.
 */
export function percent(self: number, discovery: number): BucketShare {
  const safeSelf = Number.isFinite(self) && self > 0 ? self : 0;
  const safeDiscovery = Number.isFinite(discovery) && discovery > 0 ? discovery : 0;
  const total = safeSelf + safeDiscovery;
  if (total <= 0) {
    return { self: 0, discovery: 0 };
  }
  return {
    self: (safeSelf / total) * 100,
    discovery: (safeDiscovery / total) * 100,
  };
}
