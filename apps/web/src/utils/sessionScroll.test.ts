import { describe, expect, it } from "vitest";

import { SessionScrollMemory } from "./sessionScroll";

describe("SessionScrollMemory", () => {
  it("keeps independent positions for each Session", () => {
    const memory = new SessionScrollMemory();
    memory.save("session-a", { list: 120, overview: 640 });
    memory.save("session-b", { list: 40, overview: 80 });

    expect(memory.has("session-a")).toBe(true);
    expect(memory.has("missing")).toBe(false);
    expect(memory.get("session-a")).toEqual({ list: 120, overview: 640 });
    expect(memory.get("session-b")).toEqual({ list: 40, overview: 80 });
    expect(memory.get("missing")).toEqual({ list: 0, overview: 0 });
  });

  it("normalizes offsets and can forget a removed Session", () => {
    const memory = new SessionScrollMemory();
    memory.save("session-a", { list: -4, overview: 12.6 });
    expect(memory.get("session-a")).toEqual({ list: 0, overview: 13 });
    memory.forget("session-a");
    expect(memory.get("session-a")).toEqual({ list: 0, overview: 0 });
  });
});
