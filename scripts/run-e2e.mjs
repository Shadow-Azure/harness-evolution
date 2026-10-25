#!/usr/bin/env node
// Run the small real-browser suite while accepting the historical pnpm argument form.

import { spawnSync } from "node:child_process";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";

const e2eDirectory = path.resolve("tests/e2e");
const files = readdirSync(e2eDirectory)
  .filter((file) => file.endsWith(".test.mjs"))
  .map((file) => path.join(e2eDirectory, file))
  .sort();
const requestedPattern = process.argv.slice(2).find((argument) => !argument.startsWith("-"));

function testTitles(source) {
  const pattern = /\b(?:test|it)\s*\(\s*(["'`])((?:\\.|(?!\1)[\s\S])*?)\1/g;
  return [...source.matchAll(pattern)].map((match) => match[2]);
}

if (requestedPattern) {
  let matcher;
  try {
    matcher = new RegExp(requestedPattern);
  } catch (error) {
    console.error(`run-e2e: invalid test-name pattern: ${error.message}`);
    process.exit(2);
  }
  const matched = files.some((file) =>
    testTitles(readFileSync(file, "utf8")).some((title) => matcher.test(title)),
  );
  if (!matched) {
    console.error(`run-e2e: no tests matched test-name pattern ${JSON.stringify(requestedPattern)}`);
    process.exit(2);
  }
}

const nodeArguments = ["--test"];
if (requestedPattern) {
  nodeArguments.push(`--test-name-pattern=${requestedPattern}`);
}
nodeArguments.push(...files);

const result = spawnSync(process.execPath, nodeArguments, {
  stdio: "inherit",
  timeout: Number(process.env.HE_E2E_TIMEOUT_MS ?? 180_000),
  killSignal: "SIGTERM",
});
if (result.error?.code === "ETIMEDOUT") {
  console.error("run-e2e: real-browser suite exceeded its time limit");
  process.exit(124);
}
process.exit(result.status ?? 1);
