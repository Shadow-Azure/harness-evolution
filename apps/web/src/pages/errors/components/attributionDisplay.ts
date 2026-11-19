import type {
  AttributionDetail,
  AttributionItem,
} from "@harness/contracts";

/** Visible conclusion copy; on-target and non-target are never synonyms. */
export type AttributionConclusionPresentation = {
  label: string;
  badge: string;
  tone: "green" | "orange";
};

const CONCLUSION_PRESENTATION: Record<
  AttributionItem["conclusion"],
  AttributionConclusionPresentation
> = {
  attributed: { label: "可归因", badge: "可归因", tone: "green" },
  non_target: {
    label: "非该对象问题",
    badge: "非本对象",
    tone: "orange",
  },
  inconclusive: {
    label: "证据不足",
    badge: "待补证据",
    tone: "orange",
  },
};

const CATEGORY_LABELS: Record<
  NonNullable<AttributionDetail["category"]>,
  string
> = {
  model: "模型问题",
  prompt: "prompt缺失某些提示词",
  error: "错误",
  flow: "流程",
  context: "上下文",
};

const TRIGGER_ORDER_LABELS: Record<
  AttributionDetail["triggerCompare"]["order"],
  string
> = {
  before: "位于对象触发点之前",
  after: "位于对象触发点之后",
  same: "与对象触发点同一位置",
  unknown: "触发点无法比较",
};

/**
 * Resolve the conclusion label and token tone for one attribution.
 * @param conclusion Server-owned attribution conclusion.
 * @returns Visible copy that keeps non-target distinct from unanalyzed.
 */
export function attributionConclusion(
  conclusion: AttributionItem["conclusion"],
): AttributionConclusionPresentation {
  return CONCLUSION_PRESENTATION[conclusion];
}

/**
 * Resolve the closed attribution category label.
 * @param category Server-owned category, absent for a non-target conclusion.
 * @returns Visible category copy or an explicit unclassified label.
 */
export function attributionCategory(
  category: AttributionDetail["category"],
): string {
  return category ? CATEGORY_LABELS[category] : "未分类";
}

/**
 * Resolve the trigger-order sentence for the detail comparison.
 * @param order Server-owned comparison result.
 * @returns Sentence-safe copy; unknown stays an explicit evidence gap.
 */
export function attributionTriggerOrder(
  order: AttributionDetail["triggerCompare"]["order"],
): string {
  return TRIGGER_ORDER_LABELS[order];
}
