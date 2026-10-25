#!/usr/bin/env node
// Forward development-only local session commands through the API virtualenv.

import { existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

const API_DIR = path.resolve("apps/api");
const PYTHON =
  process.platform === "win32"
    ? path.join(API_DIR, ".venv", "Scripts", "python.exe")
    : path.join(API_DIR, ".venv", "bin", "python");
const mode = process.argv[2];
const commands = new Map([
  ["import", "import-local"],
  ["verify", "verify-local"],
  ["normalize", "normalize-local"],
  ["tree", "tree-local"],
  ["replay", "replay-local"],
]);

if (!commands.has(mode)) {
  console.error(
    "local-sessions: expected `import`, `verify`, `normalize`, `tree`, or `replay`",
  );
  process.exit(2);
}
if (!existsSync(PYTHON)) {
  console.error("local-sessions: apps/api/.venv is missing; run `pnpm setup:api` first");
  process.exit(2);
}

const dataDir = path.resolve(process.env.HE_DATA_DIR ?? "data");
mkdirSync(dataDir, { recursive: true });
const databasePath = path.join(dataDir, "harness-evolution.sqlite");
const sessionsDir = path.resolve(
  process.env.HE_LOCAL_SESSIONS_DIR ?? "claude-code-sessions",
);
const result = spawnSync(
  PYTHON,
  ["-m", "app.cli", commands.get(mode), "--sessions-dir", sessionsDir],
  {
    cwd: API_DIR,
    env: {
      ...process.env,
      HE_DATA_DIR: dataDir,
      HE_DB_DIALECT: process.env.HE_DB_DIALECT ?? "sqlite",
      HE_DB_URL:
        process.env.HE_DB_URL ?? `sqlite+aiosqlite:///${databasePath}`,
      HE_JWT_SECRET:
        process.env.HE_JWT_SECRET ??
        "local-session-import-signing-secret-with-sufficient-length",
      HE_PHASE: process.env.HE_PHASE ?? "demo",
    },
    stdio: "inherit",
  },
);

if (result.error) {
  console.error("local-sessions: API command could not start");
  process.exit(1);
}
process.exit(result.status ?? 1);
