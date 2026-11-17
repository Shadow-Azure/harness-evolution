import type { EvolutionRunStep } from "@harness/contracts";
import { describe, expect, it } from "vitest";

import {
  defaultRunStepKey,
  resolveRunStepKey,
  workspacePushStatusLabel,
} from "./runDetail";

function steps(
  statuses: Array<"done" | "active" | "pending">,
): EvolutionRunStep[] {
  const keys = [
    "range",
    "sessions",
    "potential",
    "attribution",
    "clusters",
    "iteration",
    "final",
  ] as const;
  const titles = [
    "选择范围",
    "Session 关联",
    "潜在 bad case",
    "对象归因",
    "聚类与严重度",
    "迭代优化",
    "测试集终评",
  ];
  return keys.map((key, index) => ({
    key,
    index,
    title: titles[index] ?? key,
    status: statuses[index] ?? "pending",
    clickable: statuses[index] !== "pending",
    detail: key === "iteration" && statuses[index] === "active"
      ? "第 1/2 轮"
      : null,
  }));
}

describe("run detail step projection", () => {
  it("selects the backend active step and rejects a pending query target", () => {
    const projected = steps([
      "done",
      "done",
      "done",
      "done",
      "done",
      "active",
      "pending",
    ]);

    expect(projected[5]?.detail).toBe("第 1/2 轮");
    expect(defaultRunStepKey(projected)).toBe("iteration");
    expect(resolveRunStepKey("final", projected)).toBe("iteration");
    expect(resolveRunStepKey("clusters", projected)).toBe("clusters");
  });

  it("selects the last done step for completed and range while preparing", () => {
    const completed = steps([
      "done",
      "done",
      "done",
      "done",
      "done",
      "done",
      "done",
    ]);
    const preparing = steps([
      "active",
      "pending",
      "pending",
      "pending",
      "pending",
      "pending",
      "pending",
    ]);

    expect(defaultRunStepKey(completed)).toBe("final");
    expect(defaultRunStepKey(preparing)).toBe("range");
    expect(resolveRunStepKey("final", preparing)).toBe("range");
  });

  it("labels local-only push status without claiming remote success", () => {
    expect(workspacePushStatusLabel("skipped")).toBe("已跳过（本地模式）");
    expect(workspacePushStatusLabel("succeeded")).toBe("推送成功");
  });
});
