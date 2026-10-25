#!/usr/bin/env node
// Run the small real-browser suite while accepting the historical pnpm argument form.

import { spawnSync } from "node:child_process";
import { readdirSync } from "node:fs";
import path from "node:path";

const e2eDirectory = path.resolve("tests/e2e");
const files = readdirSync(e2eDirectory)
  .filter((file) => file.endsWith(".test.mjs"))
  .map((file) => path.join(e2eDirectory, file))
  .sort();
const requestedPattern = process.argv.slice(2).find((argument) => !argument.startsWith("-"));
const nodeArguments = ["--test"];
if (requestedPattern) {
  nodeArguments.push(`--test-name-pattern=${requestedPattern}`);
}
nodeArguments.push(...files);

const result = spawnSync(process.execPath, nodeArguments, {
  stdio: "inherit",
});
process.exit(result.status ?? 1);
