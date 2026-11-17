import type { RelationConfidence } from "../types";

/** Short Chinese labels for the four parent relation evidence levels. */
export const RELATION_LABELS: Record<RelationConfidence, string> = {
  authoritative: "权威",
  derived: "派生",
  synthetic: "合成",
  unresolved: "未解析",
};

/** Design-mandated warning for a child without a returned final report. */
export const MISSING_REPORT_WARNING = "未返回最终报告";
