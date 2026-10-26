// Shared performance budget for real-browser E2E and reports.

/** Runtime budgets measured in milliseconds. */
export const PERFORMANCE_BUDGETS = Object.freeze({
  cardsReadyMs: 2_500,
  largestTreeReadyMs: 2_500,
  interactionMs: 200,
  longTaskMs: 200,
  scrollFrameAverageMs: 34,
  treeExpandMs: 350,
});

/** Synthetic largest-tree shape used by CI. */
export const SYNTHETIC_LARGEST_TREE = Object.freeze({
  agents: 61,
  lines: 13_492,
});
