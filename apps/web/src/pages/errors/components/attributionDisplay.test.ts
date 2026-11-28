import { describe, expect, it } from "vitest";

import { attributionCategory } from "../../../utils/attributionCategory";
import {
  attributionConclusion,
  attributionTriggerOrder,
} from "./attributionDisplay";

describe("attribution display copy", () => {
  it("keeps a non-target conclusion distinct from unanalyzed copy", () => {
    expect(attributionConclusion("attributed")).toEqual({
      label: "可归因",
      badge: "可归因",
      tone: "green",
    });
    expect(attributionConclusion("non_target")).toEqual({
      label: "非该对象问题",
      badge: "非本对象",
      tone: "orange",
    });
  });

  it("labels categories, object types and trigger order", () => {
    expect(attributionCategory("model")).toBe("模型问题");
    expect(attributionCategory("prompt")).toBe("提示词问题");
    expect(attributionCategory("error")).toBe("错误");
    expect(attributionCategory("flow")).toBe("流程");
    expect(attributionCategory("context")).toBe("上下文");
    expect(attributionCategory("flow")).toBe("流程");
    expect(attributionCategory("context")).toBe("上下文");
    expect(attributionCategory(null)).toBe("未分类");
    expect(attributionTriggerOrder("before")).toBe("位于对象触发点之前");
    expect(attributionTriggerOrder("unknown")).toBe("触发点无法比较");
  });
});
