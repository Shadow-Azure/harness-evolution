#!/usr/bin/env node
// Run the sanitized attribution Golden Set through the API Python environment.

import { existsSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

const apiDirectory = path.resolve("apps/api");
const python =
  process.platform === "win32"
    ? path.join(apiDirectory, ".venv", "Scripts", "python.exe")
    : path.join(apiDirectory, ".venv", "bin", "python");

if (!existsSync(python)) {
  console.error("attribution:evaluate: apps/api/.venv is missing; run `pnpm setup:api` first");
  process.exit(2);
}

const forwarded = process.argv.slice(2);
if (forwarded[0] === "--") forwarded.shift();

const result = spawnSync(
  python,
  ["-m", "app.cli", "attribution-eval", ...forwarded],
  {
    cwd: apiDirectory,
    env: process.env,
    stdio: "inherit",
  },
);

process.exit(result.status ?? 1);
