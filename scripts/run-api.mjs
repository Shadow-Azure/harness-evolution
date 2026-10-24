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

const COMMANDS = {
  dev: ["-m", "app", "--reload"],
  db: ["-m", "pytest", "tests/test_database.py", "-m", "not mysql"],
  "db-mysql": ["-m", "pytest", "tests/test_database.py", "-m", "mysql", "--maxfail=1"],
  lint: ["-m", "ruff", "check", ".", "--output-format", "concise"],
  start: ["-m", "app"],
  test: [
    "-c",
    "from coverage import Coverage; c=Coverage(); c.start(); import pytest; status=pytest.main([]); c.stop(); c.save(); c.report(); raise SystemExit(status)",
  ],
  typecheck: ["-m", "mypy", "app", "tests"],
};

const command = process.argv[2];
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

const result = spawnSync(PYTHON, COMMANDS[command], {
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
