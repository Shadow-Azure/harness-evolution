#!/usr/bin/env node
// Verify that local sessions and generated SQLite data can never enter Git.

import { execFileSync } from "node:child_process";

function output(command, args) {
  try {
    return execFileSync(command, args, {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    }).trim();
  } catch (error) {
    const detail = error.stderr?.toString().trim();
    console.error(detail || "local-data: git check failed");
    process.exit(1);
  }
}

const tracked = output("git", [
  "ls-files",
  "--",
  "data",
  "claude-code-sessions",
]);
if (tracked) {
  console.error("local-data: local session or generated data files are tracked");
  process.exit(1);
}

const ignored = output("git", [
  "check-ignore",
  "--no-index",
  "data/harness.db",
  "claude-code-sessions/root.jsonl",
]).split("\n");
if (
  !ignored.includes("data/harness.db") ||
  !ignored.includes("claude-code-sessions/root.jsonl")
) {
  console.error("local-data: local data directories are not fully ignored");
  process.exit(1);
}

console.log("local-data: source and generated directories are ignored and untracked");
