#!/usr/bin/env node
// Repeatable real-browser performance report for synthetic or local data.

import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

/**
 * Return the source selected by CLI flags.
 * @param {string[]} argv Process arguments after the script name.
 * @returns {"fixture" | "local"} Selected data source.
 */
export function reportSource(argv) {
  return argv.includes("--local") ? "local" : "fixture";
}

/**
 * Run the real-browser report and always remove its temporary artifact directory.
 * @param {{
 *   argv?: string[],
 *   deps?: {
 *     makeTempDir?: () => string,
 *     readReport?: (file: string) => string,
 *     remove?: (directory: string) => void,
 *     spawn?: typeof spawnSync,
 *   },
 * }} [options] Optional process arguments and dependency seams.
 * @returns {Promise<object>} Parsed performance report.
 */
export async function createPerformanceReport(options = {}) {
  const argv = options.argv ?? process.argv.slice(2);
  const source = reportSource(argv);
  const deps = options.deps ?? {};
  const makeTempDir =
    deps.makeTempDir ??
    (() => mkdtempSync(path.join(tmpdir(), "harness-performance-")));
  const readReport =
    deps.readReport ??
    ((file) => readFileSync(file, "utf8"));
  const remove = deps.remove ?? ((directory) => rmSync(directory, { force: true, recursive: true }));
  const spawn = deps.spawn ?? spawnSync;
  const artifactDir = makeTempDir();

  try {
    const result = spawn(
      process.platform === "win32" ? "pnpm.cmd" : "pnpm",
      ["test:e2e", "--pattern", "performance budgets"],
      {
        env: {
          ...process.env,
          HE_E2E_ARTIFACT_DIR: artifactDir,
          HE_E2E_TIMEOUT_MS: process.env.HE_E2E_TIMEOUT_MS ?? "300000",
          HE_PERF_SOURCE: source,
        },
        stdio: "inherit",
      },
    );
    if (result.status !== 0) {
      throw new Error(`performance E2E exited with status ${result.status ?? 1}`);
    }
    return JSON.parse(
      readReport(path.join(artifactDir, "m3-session-performance.json")),
    );
  } finally {
    remove(artifactDir);
  }
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href
) {
  try {
    const report = await createPerformanceReport();
    console.log(JSON.stringify(report, null, 2));
  } catch (error) {
    console.error(`performance-report: ${error instanceof Error ? error.message : String(error)}`);
    process.exitCode = 1;
  }
}
