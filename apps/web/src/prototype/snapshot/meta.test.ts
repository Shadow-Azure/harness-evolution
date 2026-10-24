import { describe, expect, it } from "vitest";
import { metaLine, responseLine } from "./fixtures";
import { parseSessionMeta, toRecord } from "./meta";

describe("session metadata", () => {
  it("keeps thread identity separate from a reused session id", () => {
    const meta = parseSessionMeta(
      metaLine({
        threadId: "child-thread",
        sessionId: "root-session",
        parentThreadId: "root-thread",
        depth: 2,
        agentPath: "/root/child",
        nickname: "Ada",
      }),
      "child.jsonl",
    );

    expect(meta).toMatchObject({
      threadId: "child-thread",
      sessionId: "root-session",
      familyParentThreadId: "root-thread",
      depth: 2,
      agentPath: "/root/child",
      nickname: "Ada",
      kind: "subagent",
    });
  });

  it("classifies guardian threads as review agents", () => {
    const meta = parseSessionMeta(
      metaLine({ threadId: "guardian", sessionId: "root-session", parentThreadId: "root-thread", other: "guardian" }),
      "guardian.jsonl",
    );

    expect(meta?.kind).toBe("review");
    expect(meta?.familyParentThreadId).toBeNull();
  });

  it("preserves line and ordinal for evidence anchors", () => {
    const record = toRecord("a.jsonl", responseLine(41, { type: "message", role: "user", content: [] }), 7);

    expect(record).toMatchObject({ rolloutId: "a.jsonl", line: 7, ordinal: 41, type: "response_item" });
  });

  it("normalizes root metadata and rejects malformed input", () => {
    const root = parseSessionMeta(metaLine({ threadId: "root" }), "root.jsonl");

    expect(root).toMatchObject({ kind: "root", agentPath: "/", sessionId: "root" });
    expect(parseSessionMeta("not JSON", "bad.jsonl")).toBeNull();
    expect(parseSessionMeta(responseLine(1, { type: "message" }), "bad.jsonl")).toBeNull();
    expect(
      parseSessionMeta(
        JSON.stringify({ type: "session_meta", payload: { id: "thread" } }),
        "bad.jsonl",
      ),
    ).toMatchObject({ sessionId: "thread" });
    expect(
      parseSessionMeta(JSON.stringify({ type: "session_meta", payload: null }), "bad.jsonl"),
    ).toBeNull();
  });

  it("uses a stable epoch timestamp when metadata has no time", () => {
    const meta = parseSessionMeta(
      JSON.stringify({ type: "session_meta", payload: { id: "root", session_id: "root" } }),
      "root.jsonl",
    );

    expect(meta?.startedAt).toBe("1970-01-01T00:00:00.000Z");
  });
});
