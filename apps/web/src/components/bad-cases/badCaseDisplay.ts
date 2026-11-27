import type { BadCase } from "@harness/contracts";

import { attributionCategory } from "../../utils/attributionCategory";

/** Human label and token class for a Session problem badge. */
export type BadCaseStatePresentation = {
  label: string;
  tone: "neutral" | "green" | "purple" | "orange" | "red" | "blue";
};

/** Visible audit chip for a non-event bad-case anchor. */
export type BadCaseAnchorPresentation = {
  label: string;
  tone: "orange" | "neutral";
  description: string;
};

/** One display-safe key/value pair from external problem metadata. */
export type BadCaseFact = {
  key: string;
  value: string;
};

const STATE_PRESENTATION: Record<
  BadCase["analysis"]["displayState"],
  BadCaseStatePresentation
> = {
  unanalyzed: { label: "未分析", tone: "neutral" },
  analyzed_nonissue: { label: "非问题", tone: "green" },
  analyzed_issue_model: { label: `是问题-${attributionCategory("model")}`, tone: "purple" },
  analyzed_issue_prompt: { label: `是问题-${attributionCategory("prompt")}`, tone: "orange" },
  analyzed_issue_error: { label: `是问题-${attributionCategory("error")}`, tone: "red" },
  analyzed_issue_flow: { label: `是问题-${attributionCategory("flow")}`, tone: "blue" },
  analyzed_issue_context: { label: `是问题-${attributionCategory("context")}`, tone: "green" },
};

/**
 * Resolve the prototype label and tone for an attribution state.
 * @param displayState API display state.
 * @returns Stable visible label and token tone.
 */
export function badCaseState(
  displayState: BadCase["analysis"]["displayState"],
): BadCaseStatePresentation {
  return STATE_PRESENTATION[displayState];
}

/**
 * Describe an anchor that has no direct event coordinate.
 *
 * The API uses INT_MAX for a post-process anchor; the UI must never render that
 * sentinel as an event number, so it gets an explicit audit label instead.
 * @param anchor Backend-computed problem anchor.
 * @returns Visible chip copy, or null when the anchor is an ordinary event.
 */
export function badCaseAnchorPresentation(
  anchor: BadCase["anchor"],
): BadCaseAnchorPresentation | null {
  if (anchor.kind === "post_process") {
    return {
      label: "后处理",
      tone: "orange",
      description:
        "上报对象没有可定位的触发事件，按 post-process 锚点参与归因。",
    };
  }
  if (anchor.kind === "unknown") {
    return {
      label: "锚点未知",
      tone: "neutral",
      description: "上报 Agent 无法解析，锚点位置未知。",
    };
  }
  return null;
}

/**
 * Render compact key/value facts from external metadata.
 * @param metadata Untrusted external metadata object.
 * @returns Up to three display-safe key/value pairs.
 */
export function badCaseFactEntries(
  metadata: Record<string, unknown> | null,
): BadCaseFact[] {
  if (!metadata) return [];
  return Object.entries(metadata)
    .slice(0, 3)
    .map(([key, value]) => {
      const text =
        typeof value === "string" ? value : JSON.stringify(value);
      return {
        key,
        value: text.length > 72 ? `${text.slice(0, 71)}…` : text,
      };
    });
}
