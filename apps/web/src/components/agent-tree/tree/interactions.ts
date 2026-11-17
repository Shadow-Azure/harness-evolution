import type { InjectionKey } from "vue";

/** Select one problem card from a Vue Flow custom node. */
export const BAD_CASE_SELECT_KEY: InjectionKey<(badCaseId: string) => void> =
  Symbol("agent-tree:bad-case-select");
