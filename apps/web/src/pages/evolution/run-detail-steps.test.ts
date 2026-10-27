import type { EvolutionRunStep } from "@harness/contracts";
import { describe, expect, it } from "vitest";

import { defaultRunStepKey, resolveRunStepKey } from "./runDetail";

function steps(
  statuses: Array<"done" | "active" | "pending">,
): EvolutionRunStep[] {
  const keys = [
    "input",
    "clusters",
    "attribution",
    "severity",
    "iteration",
    "final",
  ] as const;
  const titles = [
    "筛选输入",
    "问题聚类",
    "归因确认",
    "严重程度排序",
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
      "active",
      "pending",
    ]);

    expect(projected[4]?.detail).toBe("第 1/2 轮");
    expect(defaultRunStepKey(projected)).toBe("iteration");
    expect(resolveRunStepKey("final", projected)).toBe("iteration");
    expect(resolveRunStepKey("clusters", projected)).toBe("clusters");
  });

  it("selects the last done step for completed and input while preparing", () => {
    const completed = steps(["done", "done", "done", "done", "done", "done"]);
    const preparing = steps([
      "active",
      "pending",
      "pending",
      "pending",
      "pending",
      "pending",
    ]);

    expect(defaultRunStepKey(completed)).toBe("final");
    expect(defaultRunStepKey(preparing)).toBe("input");
    expect(resolveRunStepKey("final", preparing)).toBe("input");
  });
});
