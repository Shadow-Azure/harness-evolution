#!/usr/bin/env node
// Validate fixture schemas, hashes, paths, and byte budgets without a database.

import { existsSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

const API_DIR = path.resolve("apps/api");
const PYTHON =
  process.platform === "win32"
    ? path.join(API_DIR, ".venv", "Scripts", "python.exe")
    : path.join(API_DIR, ".venv", "bin", "python");
const corpus = path.resolve(
  process.env.HE_FIXTURE_CORPUS ?? "fixtures/m2-synthetic/corpus.json",
);

if (!existsSync(PYTHON)) {
  console.error("fixtures:check: apps/api/.venv is missing; run `pnpm setup:api` first");
  process.exit(2);
}

const result = spawnSync(
  PYTHON,
  ["-m", "app.cli", "fixtures-check", "--corpus", corpus],
  {
    cwd: API_DIR,
    env: process.env,
    stdio: "inherit",
  },
);

process.exit(result.status ?? 1);
