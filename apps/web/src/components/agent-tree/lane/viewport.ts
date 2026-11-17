import type { LaneViewport } from "../types";

const MIN_ZOOM = 0.08;
const MAX_ZOOM = 3;
const FIT_PADDING = 10;
const FIT_MAX_ZOOM = 1.3;

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/**
 * Clamp a zoom factor into the supported lane viewport range.
 *
 * @param zoom Requested zoom factor.
 * @returns Zoom factor between 0.08 and 3.
 */
export function clampZoom(zoom: number): number {
  if (!Number.isFinite(zoom)) {
    return 1;
  }
  return clamp(zoom, MIN_ZOOM, MAX_ZOOM);
}

/**
 * Zoom around a pointer while keeping the content under it fixed.
 *
 * @param view Current viewport transform.
 * @param factor Multiplicative zoom factor.
 * @param pointerX Pointer x in viewport pixels.
 * @param pointerY Pointer y in viewport pixels.
 * @returns Next viewport transform.
 */
export function zoomAt(
  view: LaneViewport,
  factor: number,
  pointerX: number,
  pointerY: number,
): LaneViewport {
  const next = clampZoom(view.k * factor);
  const ratio = next / view.k;
  return {
    k: next,
    x: pointerX - (pointerX - view.x) * ratio,
    y: pointerY - (pointerY - view.y) * ratio,
  };
}

/**
 * Translate the canvas by a pointer delta.
 *
 * @param view Current viewport transform.
 * @param dx Horizontal pointer movement in pixels.
 * @param dy Vertical pointer movement in pixels.
 * @returns Next viewport transform.
 */
export function pan(view: LaneViewport, dx: number, dy: number): LaneViewport {
  return { ...view, x: view.x + dx, y: view.y + dy };
}

/**
 * Fit a content rectangle into the viewport and center it.
 *
 * @param contentWidth Canvas width in CSS pixels.
 * @param contentHeight Canvas height in CSS pixels.
 * @param viewportWidth Visible viewport width.
 * @param viewportHeight Visible viewport height.
 * @returns Centered viewport transform, never above 1.3 zoom.
 */
export function fitViewport(
  contentWidth: number,
  contentHeight: number,
  viewportWidth: number,
  viewportHeight: number,
): LaneViewport {
  if (
    contentWidth <= 0 ||
    contentHeight <= 0 ||
    viewportWidth <= 0 ||
    viewportHeight <= 0
  ) {
    return { x: 0, y: 0, k: 1 };
  }
  const k = clamp(
    Math.min(
      Math.max(160, viewportWidth - FIT_PADDING * 2) / contentWidth,
      Math.max(120, viewportHeight - FIT_PADDING * 2) / contentHeight,
    ),
    MIN_ZOOM,
    FIT_MAX_ZOOM,
  );
  return {
    k,
    x: (viewportWidth - contentWidth * k) / 2,
    y: (viewportHeight - contentHeight * k) / 2,
  };
}

/**
 * Center a content-space point in the viewport at a given zoom.
 *
 * @param view Current viewport transform; its zoom is raised to `minZoom`.
 * @param contentX Target point x in content pixels.
 * @param contentY Target point y in content pixels.
 * @param viewportWidth Visible viewport width.
 * @param viewportHeight Visible viewport height.
 * @param minZoom Zoom floor for locating a target.
 * @returns Viewport transform centering the point.
 */
export function centerOn(
  view: LaneViewport,
  contentX: number,
  contentY: number,
  viewportWidth: number,
  viewportHeight: number,
  minZoom = 0.6,
): LaneViewport {
  const k = clampZoom(Math.max(view.k, minZoom));
  return {
    k,
    x: viewportWidth / 2 - contentX * k,
    y: viewportHeight / 2 - contentY * k,
  };
}

/**
 * Reset the canvas to its native 1:1 transform at the origin.
 *
 * @returns Identity viewport transform.
 */
export function resetViewport(): LaneViewport {
  return { x: 0, y: 0, k: 1 };
}
