import { describe, expect, it } from "vitest";

import {
  densityWidth,
  formatDensity,
  formatDuration,
  formatTokens,
} from "./sessionDisplay";

describe("session display formatting", () => {
  it("formats duration boundaries with hours and minutes", () => {
    expect(formatDuration(0)).toBe("0s");
    expect(formatDuration(3)).toBe("3s");
    expect(formatDuration(60)).toBe("1m");
    expect(formatDuration(3_600)).toBe("1h");
    expect(formatDuration(63_420)).toBe("17h37m");
  });

  it("formats compact token counts with integer k and one-decimal M", () => {
    expect(formatTokens(999)).toBe("999");
    expect(formatTokens(12_400)).toBe("12k");
    expect(formatTokens(1_345_678)).toBe("1.3M");
  });

  it("keeps density text and bar width on the same scale", () => {
    expect(formatDensity(2.04)).toBe("2.0/百消息");
    expect(densityWidth(0)).toBe("0%");
    expect(densityWidth(1.5)).toBe("50%");
    expect(densityWidth(3)).toBe("100%");
    expect(densityWidth(9)).toBe("100%");
  });
});
