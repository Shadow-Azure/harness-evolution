#!/usr/bin/env node
// Create the API virtual environment and install its declared dependencies.

import { existsSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

const API_DIR = path.resolve("apps/api");
const candidates = process.platform === "win32"
  ? ["py", "-3.12", "python", "python3"]
  : ["python3.12", "python3", "python"];

function versionOf(command, prefix = []) {
  const result = spawnSync(command, [...prefix, "--version"], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (result.status !== 0) return null;
  const match = /Python (\d+)\.(\d+)/.exec(result.stdout);
  return match ? { command, prefix, major: Number(match[1]), minor: Number(match[2]) } : null;
}

const runtime = candidates
  .map((candidate) => candidate === "py" ? versionOf("py", ["-3.12"]) : versionOf(candidate))
  .find((candidate) => candidate && (candidate.major > 3 || (candidate.major === 3 && candidate.minor >= 12)));

if (!runtime) {
  console.error("setup-api: Python 3.12 or newer is required");
  process.exit(1);
}

const venv = path.join(API_DIR, ".venv");
if (!existsSync(venv)) {
  const created = spawnSync(runtime.command, [...runtime.prefix, "-m", "venv", venv], {
    stdio: "inherit",
  });
  if (created.status !== 0) process.exit(created.status ?? 1);
}

const python = process.platform === "win32"
  ? path.join(venv, "Scripts", "python.exe")
  : path.join(venv, "bin", "python");
const installed = spawnSync(
  python,
  ["-m", "pip", "install", "-e", ".[dev]"],
  { cwd: API_DIR, stdio: "inherit" },
);
process.exit(installed.status ?? 1);
