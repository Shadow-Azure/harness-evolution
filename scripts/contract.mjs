#!/usr/bin/env node
// Generate FastAPI's OpenAPI snapshot and the TypeScript types derived from it.

import { spawnSync } from "node:child_process";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

const ROOT = path.resolve(import.meta.dirname, "..");
const API_DIR = path.join(ROOT, "apps/api");
const PYTHON =
  process.platform === "win32"
    ? path.join(API_DIR, ".venv", "Scripts", "python.exe")
    : path.join(API_DIR, ".venv", "bin", "python");
const SNAPSHOT = path.join(ROOT, "packages/contracts/openapi.json");
const GENERATED = path.join(ROOT, "packages/contracts/src/generated/api.d.ts");
const GENERATED_HEADER =
  "/* This file is generated from packages/contracts/openapi.json. Do not edit. */\n" +
  "/** @generated */\n\n";

/**
 * Compare expected generated text with the checked-in text.
 * @param {string} expected canonical generated content
 * @param {string} actual checked-in content
 * @param {string} filename path used in failures
 * @param {{requireGeneratedMarker?: boolean}} [options] artifact-specific checks
 * @returns {string[]} actionable differences
 */
export function compareContractFiles(expected, actual, filename, options = {}) {
  const errors = [];
  if ((options.requireGeneratedMarker ?? true) && !actual.includes("@generated")) {
    errors.push(`${filename}: 缺少 @generated 标记；生成物禁止手写`);
  }
  if (actual !== expected) {
    errors.push(`${filename}: 内容与真实 OpenAPI 不一致；运行 \`pnpm contract:generate\``);
  }
  return errors;
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: options.cwd ?? ROOT,
    encoding: "utf8",
    env: { ...process.env, ...options.env },
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error(
      `${path.basename(command)} failed (${result.status ?? "signal"}):\n${result.stderr || result.stdout}`,
    );
  }
  return result.stdout;
}

/**
 * Export FastAPI's canonical OpenAPI JSON.
 * @returns {string} snapshot text with one trailing newline
 */
export function exportOpenApi() {
  if (!existsSync(PYTHON)) {
    throw new Error("contract: apps/api/.venv is missing; run `pnpm setup:api` first");
  }
  return run(PYTHON, ["scripts/export_openapi.py"], { cwd: API_DIR });
}

/**
 * Convert an OpenAPI snapshot into a checked-in TypeScript declaration file.
 * @param {string} snapshotText canonical OpenAPI JSON
 * @returns {Promise<string>} generated TypeScript text
 */
export async function generateTypeScript(snapshotText) {
  const { astToString, default: openapiTS } = await import("openapi-typescript");
  const ast = await openapiTS(JSON.parse(snapshotText));
  return `${GENERATED_HEADER}${astToString(ast)}`;
}

async function render(snapshotPath, generatedPath) {
  const snapshotText = exportOpenApi();
  const generatedText = await generateTypeScript(snapshotText);
  mkdirSync(path.dirname(snapshotPath), { recursive: true });
  mkdirSync(path.dirname(generatedPath), { recursive: true });
  writeFileSync(snapshotPath, snapshotText);
  writeFileSync(generatedPath, generatedText);
  return { snapshotText, generatedText };
}

/**
 * Re-render contracts into an isolated directory and compare both artifacts.
 * @returns {Promise<{ok: boolean, errors: string[]}>} check outcome
 */
export async function checkContracts() {
  const directory = mkdtempSync(path.join(tmpdir(), "harness-contracts-"));
  try {
    const temporarySnapshot = path.join(directory, "openapi.json");
    const temporaryTypes = path.join(directory, "api.d.ts");
    await render(temporarySnapshot, temporaryTypes);
    const expectedSnapshot = readFileSync(temporarySnapshot, "utf8");
    const expectedTypes = readFileSync(temporaryTypes, "utf8");
    const snapshotPath = path.relative(ROOT, SNAPSHOT);
    const typesPath = path.relative(ROOT, GENERATED);
    const errors = [];
    if (!existsSync(SNAPSHOT)) {
      errors.push(`${snapshotPath}: 文件缺失；运行 \`pnpm contract:generate\``);
    } else {
      errors.push(
        ...compareContractFiles(
          expectedSnapshot,
          readFileSync(SNAPSHOT, "utf8"),
          snapshotPath,
          { requireGeneratedMarker: false },
        ),
      );
    }
    if (!existsSync(GENERATED)) {
      errors.push(`${typesPath}: 文件缺失；运行 \`pnpm contract:generate\``);
    } else {
      errors.push(
        ...compareContractFiles(expectedTypes, readFileSync(GENERATED, "utf8"), typesPath),
      );
    }
    return { ok: errors.length === 0, errors };
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

async function main() {
  const command = process.argv[2];
  if (command === "generate") {
    await render(SNAPSHOT, GENERATED);
    console.log("contract:generate: wrote OpenAPI snapshot and TypeScript types");
    return;
  }
  if (command === "check") {
    const result = await checkContracts();
    if (!result.ok) {
      console.error(`contract:check: FAIL\n  ${result.errors.join("\n  ")}`);
      process.exit(1);
    }
    console.log("contract:check: generated contracts are current");
    return;
  }
  console.error("contract: expected `generate` or `check`");
  process.exit(2);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  await main();
}
