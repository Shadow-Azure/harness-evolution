#!/usr/bin/env node
// Build gate: prove the synchronous entry stays free of Vue Flow and exposes it dynamically.

import { gzipSync } from "node:zlib";

/** Design budget for the synchronous entry chunk before gzip. */
export const ENTRY_RAW_MAX_BYTES = 250 * 1024;
/** Design budget for the synchronous entry chunk after gzip. */
export const ENTRY_GZIP_MAX_BYTES = 90 * 1024;
/** Design budget for each manually split vendor chunk. */
export const VENDOR_RAW_MAX_BYTES = 400 * 1024;

/**
 * Validate the Vite manifest against first-screen Vue Flow boundaries.
 * @param {Record<string, {dynamicImports?: string[], file: string, isDynamicEntry?: boolean, isEntry?: boolean}>} manifest Parsed Vite build manifest.
 * @param {string} entryCode JavaScript source of the synchronous entry chunk.
 * @returns {void} Throws when the Vue Flow boundary is violated.
 */
/**
 * Find the synchronous application entry in a Vite manifest.
 * @param {Record<string, {isEntry?: boolean}>} manifest Parsed Vite build manifest.
 * @returns {NonNullable<Parameters<typeof assertFirstScreenExcludesVueFlow>[0][string]>} entry chunk.
 */
function findEntryChunk(manifest) {
  const entry = Object.values(manifest).find((chunk) => chunk.isEntry);
  if (!entry) {
    throw new Error("bundle gate could not find the Vite entry chunk");
  }
  return entry;
}

/**
 * Collect the synchronous import closure starting at a manifest chunk.
 * @param {Record<string, {imports?: string[], ...}>} manifest Parsed Vite build manifest.
 * @param {string} root manifest key to start from.
 * @returns {string[]} reachable synchronous manifest keys.
 */
function collectSynchronousChunks(manifest, root) {
  const seen = new Set([root]);
  const queue = [root];
  while (queue.length) {
    const key = queue.shift();
    for (const imported of manifest[key]?.imports ?? []) {
      if (!seen.has(imported)) {
        seen.add(imported);
        queue.push(imported);
      }
    }
  }
  return [...seen];
}

/**
 * Check whether a dynamic route reaches an isolated Vue Flow chunk.
 * @param {Record<string, {dynamicImports?: string[], imports?: string[], ...}>} manifest Parsed manifest.
 * @param {ReturnType<typeof findEntryChunk>} entry application entry chunk.
 * @returns {boolean} true when dynamic closure contains a Vue Flow vendor chunk.
 */
function dynamicClosureReachesVueFlow(manifest, entry) {
  const seen = new Set();
  const queue = entry.dynamicImports ?? [];
  while (queue.length) {
    const key = queue.shift();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    if (/vendor-vue-flow|@vue-flow\/core/.test(key)) return true;
    queue.push(...(manifest[key]?.imports ?? []));
  }
  return false;
}

/**
 * Validate static design budgets for the entry and manual vendor chunks.
 * @param {Record<string, {file: string, isEntry?: boolean, name?: string}>} manifest Parsed Vite manifest.
 * @param {(file: string) => Uint8Array} readAsset Asset reader keyed by manifest file path.
 * @returns {{entry: {raw: number, gzip: number}, vendors: Record<string, number>}} Measured bytes.
 */
export function assertBundleBudgets(manifest, readAsset) {
  const entry = findEntryChunk(manifest);
  const entryBytes = readAsset(entry.file);
  const entryGzipBytes = gzipSync(entryBytes).byteLength;
  if (entryBytes.byteLength > ENTRY_RAW_MAX_BYTES) {
    throw new Error(`entry bundle exceeds ${ENTRY_RAW_MAX_BYTES} bytes`);
  }
  if (entryGzipBytes > ENTRY_GZIP_MAX_BYTES) {
    throw new Error(`entry bundle gzip exceeds ${ENTRY_GZIP_MAX_BYTES} bytes`);
  }

  const vendors = {};
  for (const [key, chunk] of Object.entries(manifest)) {
    if (!/(?:^|[/_-])vendor-/.test(`${key} ${chunk.name ?? ""}`)) continue;
    const bytes = readAsset(chunk.file).byteLength;
    vendors[key] = bytes;
    if (bytes > VENDOR_RAW_MAX_BYTES) {
      throw new Error(`vendor chunk ${key} exceeds ${VENDOR_RAW_MAX_BYTES} bytes`);
    }
  }
  return {
    entry: { gzip: entryGzipBytes, raw: entryBytes.byteLength },
    vendors,
  };
}

/**
 * Validate the Vite manifest against first-screen Vue Flow boundaries.
 * @param {Record<string, {dynamicImports?: string[], file: string, imports?: string[], isDynamicEntry?: boolean, isEntry?: boolean}>} manifest Parsed Vite build manifest.
 * @param {string} entryCode JavaScript source of the synchronous entry chunk.
 * @returns {void} Throws when the Vue Flow boundary is violated.
 */
export function assertFirstScreenExcludesVueFlow(manifest, entryCode) {
  const entry = findEntryChunk(manifest);
  const entryKey = Object.keys(manifest).find((key) => manifest[key].isEntry) ?? "";
  const synchronousChunks = collectSynchronousChunks(manifest, entryKey);
  if (
    synchronousChunks.some((key) => /vendor-vue-flow|@vue-flow\/core/.test(key)) ||
    /import\s+[^;]*vendor-vue-flow|from\s+["'][^"']*vendor-vue-flow/.test(entryCode)
  ) {
    throw new Error("Vue Flow leaked into the first screen bundle");
  }

  if (!dynamicClosureReachesVueFlow(manifest, entry)) {
    throw new Error("the evolution route must dynamically reach a vendor-vue-flow chunk");
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const { readFile } = await import("node:fs/promises");
  const { readFileSync } = await import("node:fs");
  const manifestPath = new URL("../apps/web/dist/.vite/manifest.json", import.meta.url);
  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  const entry = Object.values(manifest).find((chunk) => chunk.isEntry);
  if (!entry) throw new Error("bundle gate could not find the Vite entry chunk");
  const entryCode = await readFile(new URL(`../apps/web/dist/${entry.file}`, import.meta.url), "utf8");
  assertFirstScreenExcludesVueFlow(manifest, entryCode);
  const readAsset = (file) =>
    readFileSync(new URL(`../apps/web/dist/${file}`, import.meta.url));
  const measured = assertBundleBudgets(manifest, readAsset);
  console.log(
    `verify-bundle: Vue Flow isolated; entry ${measured.entry.raw}B raw / ${measured.entry.gzip}B gzip; vendors ${JSON.stringify(measured.vendors)}`,
  );
}
