import { describe, expect, it } from "vitest";
import { buildFamilyIndex } from "./family-index";
import { EXAMPLE_FINDINGS } from "./findings.fixture";
import { measureFamily } from "./measure";
import { createNodeSnapshotSource } from "./node-source";
import { resolveFinding } from "./evidence";

const localRoot = process.env.HARNESS_SNAPSHOT_ROOT;
const roots = [
  "01a14ee6-d117-7c71-84a7-32b46bb3a99b",
  "01a14e5b-5d48-7382-9fed-1d2295a163c1",
  "01a14c79-9e02-7210-ada9-ae4ff5c6ae05",
  "01a14d49-f4a0-7c31-ad9a-b6e3c034501a",
];

describe.skipIf(!localRoot)("local four-family acceptance", () => {
  it("reproduces the 64/25,170/72.2MB/depth-4 baseline without eager record reads", async () => {
    const base = createNodeSnapshotSource(localRoot!);
    let recordReads = 0;
    const source = {
      listRollouts: () => base.listRollouts(),
      readMeta: (rolloutId: string) => base.readMeta(rolloutId),
      readRecords: async (rolloutId: string) => {
        recordReads += 1;
        return base.readRecords(rolloutId);
      },
    };

    const index = await buildFamilyIndex({ roots, source, findings: EXAMPLE_FINDINGS });
    expect(index.families).toHaveLength(4);
    expect(recordReads).toBe(0);

    const measured = await Promise.all(
      index.families.map((family) => measureFamily({ family, source })),
    );
    expect(measured.reduce((sum, family) => sum + family.stats.rolloutCount, 0)).toBe(64);
    expect(measured.reduce((sum, family) => sum + (family.stats.recordCount ?? 0), 0)).toBe(25170);
    expect(
      measured.reduce((sum, family) => sum + (family.stats.continuationRecordCount ?? 0), 0),
    ).toBe(12);
    expect(measured.reduce((sum, family) => sum + family.stats.byteCount, 0)).toBeGreaterThan(
      75_000_000,
    );
    expect(measured.reduce((max, family) => Math.max(max, family.stats.maxDepth), 0)).toBe(4);

    for (const family of measured) {
      for (const finding of family.findings) {
        const resolved = await resolveFinding({ finding, family, source });
        expect(resolved.evidence.length).toBeGreaterThanOrEqual(2);
      }
    }
  });
});
