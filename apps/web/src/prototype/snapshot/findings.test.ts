import { describe, expect, it } from "vitest";
import { buildFamilyIndex } from "./family-index";
import { evidenceForRecord, resolveFinding } from "./evidence";
import { EXAMPLE_FINDINGS } from "./findings.fixture";
import { metaLine, responseLine } from "./fixtures";
import { createMemorySnapshotSource } from "./memory-source";
import { toRecord } from "./meta";

describe("example findings", () => {
  it("contains at least three cross-agent findings with stable anchors", () => {
    expect(EXAMPLE_FINDINGS.length).toBeGreaterThanOrEqual(3);
    for (const finding of EXAMPLE_FINDINGS) {
      expect(new Set(finding.sourceAgentThreadIds).size).toBeGreaterThanOrEqual(2);
      expect(finding.attribution.target.id).toMatch(/^(skill|agent):/);
      expect(finding.evidence.length).toBeGreaterThanOrEqual(2);
      for (const anchor of finding.evidence) {
        expect(anchor.id).toBe(`${anchor.rolloutId}#${anchor.ordinal}`);
      }
    }
  });

  it("resolves an evidence ordinal back to its current line and call id", async () => {
    const source = createMemorySnapshotSource({
      "root.jsonl": [metaLine({ threadId: "r" })],
      "a.jsonl": [
        metaLine({ threadId: "a", parentThreadId: "r", depth: 1, agentPath: "/root/a", nickname: "A" }),
        responseLine(1, {
          type: "function_call",
          call_id: "call-1",
          name: "exec_command",
          arguments: JSON.stringify({ cmd: "cat skills/foo/SKILL.md" }),
        }),
      ],
    });
    const index = await buildFamilyIndex({ roots: ["r"], source });
    const family = index.families[0];
    if (!family) throw new Error("family missing");
    const agent = family.agents.find((candidate) => candidate.threadId === "a");
    if (!agent) throw new Error("agent missing");
    const record = toRecord(
      "a.jsonl",
      responseLine(1, {
        type: "function_call",
        call_id: "call-1",
        name: "exec_command",
        arguments: JSON.stringify({ cmd: "cat skills/foo/SKILL.md" }),
      }),
      2,
    );
    if (!record) throw new Error("record missing");
    const anchor = evidenceForRecord(agent, record, { excerpt: "skills/foo/SKILL.md" });
    const finding = {
      ...EXAMPLE_FINDINGS[0]!,
      familyRootThreadId: "r",
      sourceAgentThreadIds: ["a"],
      attribution: {
        ...EXAMPLE_FINDINGS[0]!.attribution,
        target: { type: "agent" as const, id: "agent:a", name: "A" },
      },
      evidence: [anchor],
    };

    const resolved = await resolveFinding({ finding, family, source });

    expect(resolved.target.type).toBe(finding.attribution.target.type);
    expect(resolved.evidence[0]).toMatchObject({
      rolloutId: "a.jsonl",
      ordinal: 1,
      line: 2,
      callId: "call-1",
      agentThreadId: "a",
    });
  });

  it("rejects targets and anchors that cannot be resolved", async () => {
    const source = createMemorySnapshotSource({
      "root.jsonl": [metaLine({ threadId: "r" })],
    });
    const index = await buildFamilyIndex({ roots: ["r"], source });
    const family = index.families[0];
    if (!family) throw new Error("family missing");
    const base = {
      ...EXAMPLE_FINDINGS[0]!,
      familyRootThreadId: "r",
      evidence: [],
    };

    await expect(
      resolveFinding({
        finding: {
          ...base,
          attribution: {
            ...base.attribution,
            target: { type: "agent", id: "agent:missing", name: "" },
          },
        },
        family,
        source,
      }),
    ).rejects.toThrow("不在家族");
    await expect(
      resolveFinding({
        finding: {
          ...base,
          attribution: {
            ...base.attribution,
            target: { type: "skill", id: "Skill:Invalid", name: "Invalid" },
          },
        },
        family,
        source,
      }),
    ).rejects.toThrow("invalid skill target");
    await expect(
      resolveFinding({
        finding: { ...base, familyRootThreadId: "other" },
        family,
        source,
      }),
    ).rejects.toThrow("不是 r");
    await expect(
      resolveFinding({
        finding: {
          ...base,
          attribution: {
            ...base.attribution,
            target: { type: "skill", id: "skill:test", name: "test" },
          },
          evidence: [{ ...EXAMPLE_FINDINGS[1]!.evidence[0]!, rolloutId: "missing.jsonl" }],
        },
        family,
        source,
      }),
    ).rejects.toThrow("不在家族");
    await expect(
      resolveFinding({
        finding: {
          ...base,
          attribution: {
            ...base.attribution,
            target: { type: "skill", id: "skill:test", name: "test" },
          },
          evidence: [
            { ...EXAMPLE_FINDINGS[0]!.evidence[0]!, rolloutId: "root.jsonl", ordinal: 99 },
          ],
        },
        family,
        source,
      }),
    ).rejects.toThrow("ordinal 99");
  });
});
