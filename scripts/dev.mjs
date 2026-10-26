#!/usr/bin/env node
// Run the API and web dev servers together without adding a process-manager
// dependency. Signals are forwarded so Ctrl+C shuts both children down.

import { spawn } from "node:child_process";

const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
// Node ≥18.20/20.12/22 refuses to spawn .cmd shims without a shell
// (CVE-2024-27980 hardening), so Windows must go through cmd.exe.
const spawnOptions = { stdio: "inherit", shell: process.platform === "win32" };
const processes = ["dev:api", "dev:web"].map((script) =>
  spawn(pnpm, [script], spawnOptions),
);

let stopping = false;
function stop(signal = "SIGTERM") {
  if (stopping) return;
  stopping = true;
  for (const child of processes) {
    if (!child.killed) child.kill(signal);
  }
}

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.once(signal, () => stop(signal));
}

for (const child of processes) {
  child.once("exit", (code, signal) => {
    if (!stopping && (code ?? 0) !== 0) process.exitCode = code ?? 1;
    if ((code ?? 0) !== 0 || signal) stop();
  });
}
