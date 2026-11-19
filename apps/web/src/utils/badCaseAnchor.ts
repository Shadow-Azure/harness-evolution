import type { BadCase } from "@harness/contracts";

/**
 * INT_MAX sentinel for a post-process anchor.
 *
 * The value is a sort coordinate, not an index into `events[]`; callers must
 * never use it to look up an event.
 */
export const POST_PROCESS_EVENT_INDEX = 2_147_483_647;

/**
 * Return the event index only when the anchor really points at an event.
 *
 * The returned value is a candidate coordinate; callers must still check it
 * against the host's `events[]` because an event may have been dropped.
 * @param anchor Backend-computed bad-case anchor.
 * @returns A non-sentinel event index, or null for node/post-process/unknown anchors.
 */
export function eventAnchorIndex(
  anchor: BadCase["anchor"],
): number | null {
  if (anchor.kind !== "event") {
    return null;
  }
  if (
    anchor.eventIndex < 0 ||
    anchor.eventIndex === POST_PROCESS_EVENT_INDEX
  ) {
    return null;
  }
  return anchor.eventIndex;
}

/**
 * Return the audit badge for an anchor that has no event coordinate.
 * @param anchor Backend-computed bad-case anchor.
 * @returns `后处理` for post-process anchors, otherwise null.
 */
export function anchorBadgeLabel(anchor: BadCase["anchor"]): string | null {
  return anchor.kind === "post_process" ? "后处理" : null;
}
