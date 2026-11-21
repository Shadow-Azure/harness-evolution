#!/usr/bin/env node
// Thin cross-platform wrapper around the API virtual environment. The Python
// package remains outside the pnpm workspace; this script only forwards
// developer commands and keeps CI/local invocations identical.

import { existsSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

const API_DIR = path.resolve("apps/api");
const PYTHON =
  process.platform === "win32"
    ? path.join(API_DIR, ".venv", "Scripts", "python.exe")
    : path.join(API_DIR, ".venv", "bin", "python");

// pytest-cov merges the per-worker data files that xdist leaves behind, so the
// branch threshold stays one number for serial and parallel runs alike. The
// 90% gate only applies to a full-suite run: a focused path selection cannot
// reach the threshold by design.
const TEST_ARGS = [
  "-m",
  "pytest",
  "--cov=app",
  "--cov-branch",
  "--cov-report=term-missing",
  "--durations=25",
];

const VALUE_OPTIONS = new Set([
  "-k",
  "-m",
  "-n",
  "-p",
  "--deselect",
  "--durations",
  "--dist",
  "--ignore",
  "--maxfail",
  "--timeout",
]);

/** Whether the forwarded arguments select specific tests instead of the whole suite. */
function selectsTests(arguments_) {
  for (let index = 0; index < arguments_.length; index += 1) {
    const argument = arguments_[index];
    if (argument.startsWith("-")) {
      if (VALUE_OPTIONS.has(argument)) index += 1;
      continue;
    }
    return true;
  }
  return false;
}

const COMMANDS = {
  dev: ["-m", "app", "--reload"],
  db: ["-m", "pytest", "tests/test_database.py", "-m", "not mysql"],
  "db-mysql": [
    "-m",
    "pytest",
    "tests/test_database.py",
    "tests/m11-05-v2-cross-stack",
    "tests/m12-02-external-contract-live",
    "-m",
    "mysql",
    "--maxfail=1",
  ],
  lint: ["-m", "ruff", "check", ".", "--output-format", "concise"],
  start: ["-m", "app"],
  test: TEST_ARGS,
  "test:serial": TEST_ARGS,
  typecheck: ["-m", "mypy", "app", "tests"],
};

/** Whether the caller already chose a worker count or asked for serial execution. */
function selectsWorkers(arguments_) {
  return arguments_.some(
    (argument) =>
      argument === "-n" ||
      /^-n\d+$/.test(argument) ||
      argument.startsWith("--numprocesses") ||
      argument === "--serial",
  );
}

const command = process.argv[2];
const commandArguments = process.argv.slice(3);
if (!Object.hasOwn(COMMANDS, command)) {
  console.error(`run-api: expected one of ${Object.keys(COMMANDS).join(", ")}`);
  process.exit(2);
}

if (!existsSync(PYTHON)) {
  console.error("run-api: apps/api/.venv is missing; run `pnpm setup:api` first");
  process.exit(2);
}

const lintFormat =
  command === "lint" ? spawnSync(PYTHON, ["-m", "ruff", "format", "--check", "."], {
    cwd: API_DIR,
    stdio: "inherit",
  }) : { status: 0 };
if (lintFormat.status !== 0) process.exit(lintFormat.status ?? 1);

let commandLine = [...COMMANDS[command]];
if (command === "test" || command === "test:serial") {
  // pnpm forwards a literal `--`; pytest treats it as the end of options.
  const forwarded = commandArguments.filter((argument) => argument !== "--");
  const serial = command === "test:serial" || forwarded.includes("--serial");
  const passthrough = forwarded.filter((argument) => argument !== "--serial");
  // Local runs use the machine's cores; CI passes an explicit `-n 4`.
  const workers = serial || selectsWorkers(passthrough) ? [] : ["-n", "auto"];
  // A focused selection does not represent the suite gate: skip coverage
  // instead of judging a subset against the whole-app 90% threshold.
  const coverage = selectsTests(passthrough) ? ["--no-cov"] : ["--cov-fail-under=90"];
  commandLine = [...commandLine, ...coverage, ...workers, ...passthrough];
}

const result = spawnSync(PYTHON, commandLine, {
  cwd: API_DIR,
  env:
    command === "dev"
      ? {
          ...process.env,
          HE_DB_DIALECT: process.env.HE_DB_DIALECT ?? "sqlite",
          HE_DOCS_ENABLED: process.env.HE_DOCS_ENABLED ?? "true",
        }
      : process.env,
  stdio: "inherit",
});
if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}
process.exit(result.status ?? 1);
