import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { metaLine, responseLine } from "./fixtures";
import { createNodeSnapshotSource } from "./node-source";

let tempRoot: string | null = null;

afterEach(async () => {
  if (tempRoot) {
    await rm(tempRoot, { recursive: true, force: true });
    tempRoot = null;
  }
});

describe("createNodeSnapshotSource", () => {
  it("lists nested rollouts and reads only the requested file", async () => {
    tempRoot = await mkdtemp(path.join(tmpdir(), "harness-snapshot-"));
    await mkdir(path.join(tempRoot, "2026/10/18"), { recursive: true });
    await writeFile(
      path.join(tempRoot, "2026/10/18/root.jsonl"),
      `${metaLine({ threadId: "r" })}\n${responseLine(1, { type: "message", role: "user", content: [] })}\n`,
      "utf8",
    );
    await writeFile(
      path.join(tempRoot, "2026/10/18/a.jsonl"),
      `${metaLine({ threadId: "a", parentThreadId: "r", depth: 1, agentPath: "/root/a" })}\n`,
      "utf8",
    );

    const source = createNodeSnapshotSource(tempRoot);
    const files = await source.listRollouts();
    const meta = await source.readMeta("2026/10/18/a.jsonl");
    const records = await source.readRecords("2026/10/18/root.jsonl");

    expect(files.map((file) => file.rolloutId)).toEqual([
      "2026/10/18/a.jsonl",
      "2026/10/18/root.jsonl",
    ]);
    expect(meta.threadId).toBe("a");
    expect(records.map((record) => record.ordinal)).toEqual([0, 1]);
  });
});
