import { describe, expect, it } from "vitest";
import { createMemorySnapshotSource } from "./memory-source";
import { metaLine, responseLine } from "./fixtures";

describe("memory snapshot source", () => {
  it("reads metadata without reading records", async () => {
    const source = createMemorySnapshotSource({
      "root.jsonl": [
        metaLine({ threadId: "root" }),
        responseLine(1, { type: "message", role: "user", content: [{ type: "input_text", text: "hello" }] }),
      ],
    });

    const files = await source.listRollouts();
    const meta = await source.readMeta("root.jsonl");

    expect(files).toHaveLength(1);
    expect(meta.threadId).toBe("root");
    expect(source.calls.readMeta).toBe(1);
    expect(source.calls.readRecords).toBe(0);
    expect(source.calls.metaRolloutIds).toEqual(["root.jsonl"]);
  });

  it("returns every record on demand", async () => {
    const source = createMemorySnapshotSource({
      "root.jsonl": [
        metaLine({ threadId: "root" }),
        responseLine(1, { type: "message", role: "user", content: [] }),
      ],
    });

    const records = await source.readRecords("root.jsonl");

    expect(records.map((record) => record.ordinal)).toEqual([0, 1]);
    expect(source.calls.readRecords).toBe(1);
    expect(source.calls.recordsRolloutIds).toEqual(["root.jsonl"]);
  });

  it("reports missing, empty, and malformed rollouts", async () => {
    const source = createMemorySnapshotSource({
      "empty.jsonl": [],
      "invalid.jsonl": ['{"type":"response_item","payload":{"type":"message"}}'],
    });

    await expect(source.readMeta("empty.jsonl")).rejects.toThrow("empty rollout");
    await expect(source.readMeta("invalid.jsonl")).rejects.toThrow("invalid session_meta");
    await expect(source.readRecords("missing.jsonl")).rejects.toThrow("missing rollout");
  });
});
