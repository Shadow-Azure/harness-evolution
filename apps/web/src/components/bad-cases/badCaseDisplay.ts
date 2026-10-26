import type { BadCase } from "@harness/contracts";

/** Human label and token class for one five-state attribution value. */
export type BadCaseStatePresentation = {
  label: string;
  tone: "neutral" | "green" | "purple" | "orange" | "red";
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
  analyzed_issue_model: { label: "是问题-模型问题", tone: "purple" },
  analyzed_issue_prompt: {
    label: "是问题-prompt缺失某些提示词",
    tone: "orange",
  },
  analyzed_issue_error: { label: "是问题-错误", tone: "red" },
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
 * Return the short attribution summary shown under a problem title.
 * @param problem Read-only problem detail.
 * @returns User-facing summary.
 */
export function badCaseSummary(problem: BadCase): string {
  if (problem.analysis.status === "analyzed_issue") {
    return problem.analysis.result.summary;
  }
  if (problem.analysis.status === "analyzed_nonissue") {
    return problem.analysis.result.reason;
  }
  return "尚未完成归因分析";
}

/**
 * Render compact key/value facts from external metadata.
 * @param metadata Untrusted external metadata object.
 * @returns Up to three display-safe facts.
 */
export function badCaseFacts(
  metadata: Record<string, unknown> | null,
): string[] {
  return badCaseFactEntries(metadata).map(
    (fact) => `${fact.key}=${fact.value}`,
  );
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
