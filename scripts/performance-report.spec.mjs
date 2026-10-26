import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  createPerformanceReport,
  reportSource,
} from "./performance-report.mjs";

describe("performance report", () => {
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
