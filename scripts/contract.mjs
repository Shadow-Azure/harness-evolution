#!/usr/bin/env node
// Generate FastAPI's OpenAPI snapshot, TypeScript types, and real response fixtures.

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
import { pathToFileURL } from "node:url";

const ROOT = path.resolve(import.meta.dirname, "..");
const API_DIR = path.join(ROOT, "apps/api");
const PYTHON =
  process.platform === "win32"
    ? path.join(API_DIR, ".venv", "Scripts", "python.exe")
    : path.join(API_DIR, ".venv", "bin", "python");
const SNAPSHOT = path.join(ROOT, "packages/contracts/openapi.json");
const GENERATED = path.join(ROOT, "packages/contracts/src/generated/api.d.ts");
const GENERATED_FIXTURES = path.join(
  ROOT,
  "packages/contracts/src/generated/health-fixtures.ts",
);
const FIXTURES = path.join(ROOT, "packages/contracts/fixtures/health.json");
const GENERATED_HEADER =
  "/* This file is generated from packages/contracts/openapi.json. Do not edit. */\n" +
  "/** @generated */\n\n";
const GENERATED_FIXTURES_HEADER =
  "/* This file is generated from packages/contracts/fixtures/health.json. Do not edit. */\n" +
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
 * Export canonical FastAPI health responses for compile-time contract checks.
 * @returns {string} fixture text with one trailing newline
 */
export function exportHealthFixtures() {
  return run(PYTHON, ["scripts/export_health_fixtures.py"], { cwd: API_DIR });
}

/**
 * Convert canonical response JSON into a typed, importable fixture module.
 * @param {string} fixturesText canonical health fixture JSON
 * @returns {string} generated TypeScript fixture text
 */
export function generateHealthFixtures(fixturesText) {
  const fixtures = JSON.parse(fixturesText);
  const value = JSON.stringify(fixtures, null, 2);
  return `${GENERATED_FIXTURES_HEADER}import type { HealthResponse } from "../index.js";\n\n/** Canonical FastAPI health responses used to prove cross-stack payload compatibility. */\nexport const healthFixtures = ${value} as const satisfies {\n  healthy: HealthResponse;\n  unavailable: HealthResponse;\n};\n`;
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

async function render(snapshotPath, generatedPath, fixturesPath) {
  const snapshotText = exportOpenApi();
  const generatedText = await generateTypeScript(snapshotText);
  const fixturesText = exportHealthFixtures();
  const generatedFixturesText = generateHealthFixtures(fixturesText);
  mkdirSync(path.dirname(snapshotPath), { recursive: true });
  mkdirSync(path.dirname(generatedPath), { recursive: true });
  mkdirSync(path.dirname(fixturesPath), { recursive: true });
  writeFileSync(snapshotPath, snapshotText);
  writeFileSync(generatedPath, generatedText);
  writeFileSync(fixturesPath, fixturesText);
  writeFileSync(GENERATED_FIXTURES, generatedFixturesText);
  return { snapshotText, generatedText, generatedFixturesText, fixturesText };
}

/**
 * Re-render contracts into an isolated directory and compare all artifacts.
 * @param {string} [snapshotPathOverride] checked OpenAPI artifact to verify
 * @param {string} [generatedPathOverride] checked TypeScript artifact to verify
 * @param {string} [fixturesPathOverride] checked health fixture to verify
 * @returns {Promise<{ok: boolean, errors: string[]}>} check outcome
 */
export async function checkContracts(
  snapshotPathOverride = process.env.HE_CONTRACT_SNAPSHOT ?? SNAPSHOT,
  generatedPathOverride = process.env.HE_CONTRACT_TYPES ?? GENERATED,
  fixturesPathOverride = process.env.HE_CONTRACT_FIXTURES ?? FIXTURES,
) {
  const directory = mkdtempSync(path.join(tmpdir(), "harness-contracts-"));
  try {
    const temporarySnapshot = path.join(directory, "openapi.json");
    const temporaryTypes = path.join(directory, "api.d.ts");
    const temporaryFixtures = path.join(directory, "health.json");
    await render(temporarySnapshot, temporaryTypes, temporaryFixtures);
    const expectedSnapshot = readFileSync(temporarySnapshot, "utf8");
    const expectedTypes = readFileSync(temporaryTypes, "utf8");
    const expectedFixtures = readFileSync(temporaryFixtures, "utf8");
    const expectedGeneratedFixtures = generateHealthFixtures(expectedFixtures);
    const snapshotName = path.relative(ROOT, snapshotPathOverride);
    const typesName = path.relative(ROOT, generatedPathOverride);
    const generatedFixturesName = path.relative(ROOT, GENERATED_FIXTURES);
    const fixturesName = path.relative(ROOT, fixturesPathOverride);
    const errors = [];
    for (const [expected, checkedPath, name, marker] of [
      [expectedSnapshot, snapshotPathOverride, snapshotName, false],
      [expectedTypes, generatedPathOverride, typesName, true],
      [expectedGeneratedFixtures, GENERATED_FIXTURES, generatedFixturesName, true],
      [expectedFixtures, fixturesPathOverride, fixturesName, false],
    ]) {
      if (!existsSync(checkedPath)) {
        errors.push(`${name}: 文件缺失；运行 \`pnpm contract:generate\``);
        continue;
      }
      errors.push(
        ...compareContractFiles(expected, readFileSync(checkedPath, "utf8"), name, {
          requireGeneratedMarker: marker,
        }),
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
    const snapshot = process.env.HE_CONTRACT_SNAPSHOT ?? SNAPSHOT;
    const generated = process.env.HE_CONTRACT_TYPES ?? GENERATED;
    const fixtures = process.env.HE_CONTRACT_FIXTURES ?? FIXTURES;
    await render(snapshot, generated, fixtures);
    console.log("contract:generate: wrote OpenAPI snapshot, TypeScript types, and health fixtures");
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

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
