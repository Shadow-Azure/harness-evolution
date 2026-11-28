import type { AttributionDetail } from "@harness/contracts";

const CATEGORY_LABELS: Record<
  NonNullable<AttributionDetail["category"]>,
  string
> = {
  model: "模型问题",
  prompt: "提示词问题",
  error: "错误",
  flow: "流程",
  context: "上下文",
};

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
