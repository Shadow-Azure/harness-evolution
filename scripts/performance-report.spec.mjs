import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  createPerformanceReport,
  reportSource,
} from "./performance-report.mjs";
import {
  PERFORMANCE_BUDGETS,
  SYNTHETIC_LARGEST_TREE,
} from "./performance-budgets.mjs";

describe("performance report", () => {
  it("keeps the CI budgets explicit and ordered", () => {
    assert.equal(PERFORMANCE_BUDGETS.cardsReadyMs, 2_500);
    assert.equal(PERFORMANCE_BUDGETS.treeExpandMs, 350);
    assert.equal(PERFORMANCE_BUDGETS.interactionMs, 200);
    assert.equal(PERFORMANCE_BUDGETS.longTaskMs, 200);
    assert.equal(PERFORMANCE_BUDGETS.scrollFrameAverageMs, 34);
    assert.equal(SYNTHETIC_LARGEST_TREE.agents, 61);
    assert.equal(SYNTHETIC_LARGEST_TREE.lines, 13_492);
  });

  it("selects local mode only from the explicit flag", () => {
    assert.equal(reportSource([]), "fixture");
    assert.equal(reportSource(["--local"]), "local");
  });

  it("passes the source to E2E and returns the report", async () => {
    let receivedEnv;
    const report = await createPerformanceReport({
      argv: ["--local"],
      deps: {
        makeTempDir: () => "/tmp/performance-report-fixture",
        readReport: () =>
          JSON.stringify({
            browser: { product: "Chrome/142" },
            source: "local",
          }),
        remove: () => {},
        spawn: (_command, _args, options) => {
          receivedEnv = options.env;
          return { status: 0 };
        },
      },
    });

    assert.equal(receivedEnv.HE_PERF_SOURCE, "local");
    assert.equal(report.source, "local");
  });

  it("removes the temporary directory after E2E failure", async () => {
    let removed = false;
    await assert.rejects(
      createPerformanceReport({
        deps: {
          makeTempDir: () => "/tmp/performance-report-failure",
          readReport: () => "",
          remove: () => {
            removed = true;
          },
          spawn: () => ({ status: 2 }),
        },
      }),
      /status 2/,
    );
    assert.equal(removed, true);
  });
});
