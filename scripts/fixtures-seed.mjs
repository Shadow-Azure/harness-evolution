#!/usr/bin/env node
// Forward the development-only M1 seed command through the API virtualenv.

import { existsSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

const API_DIR = path.resolve("apps/api");
const PYTHON =
  process.platform === "win32"
    ? path.join(API_DIR, ".venv", "Scripts", "python.exe")
    : path.join(API_DIR, ".venv", "bin", "python");

if (!existsSync(PYTHON)) {
  console.error("fixtures:seed: apps/api/.venv is missing; run `pnpm setup:api` first");
  process.exit(2);
}

const result = spawnSync(
  PYTHON,
  [
    "-m",
    "app.cli",
    "seed",
    "--manifest",
    path.resolve("fixtures/m1-shell.json"),
  ],
  {
    cwd: API_DIR,
    env: {
      ...process.env,
      HE_DB_DIALECT: process.env.HE_DB_DIALECT ?? "sqlite",
      HE_JWT_SECRET:
        process.env.HE_JWT_SECRET ??
        "local-fixture-seed-signing-secret-with-sufficient-length",
      HE_PHASE: process.env.HE_PHASE ?? "demo",
    },
    stdio: "inherit",
  },
);

process.exit(result.status ?? 1);
