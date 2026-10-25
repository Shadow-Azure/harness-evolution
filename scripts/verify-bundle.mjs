#!/usr/bin/env node
// Build gate: prove the synchronous entry stays free of Vue Flow and exposes it dynamically.

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
  const manifestPath = new URL("../apps/web/dist/.vite/manifest.json", import.meta.url);
  const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
  const entry = Object.values(manifest).find((chunk) => chunk.isEntry);
  if (!entry) throw new Error("bundle gate could not find the Vite entry chunk");
  const entryCode = await readFile(new URL(`../apps/web/dist/${entry.file}`, import.meta.url), "utf8");
  assertFirstScreenExcludesVueFlow(manifest, entryCode);
  console.log("verify-bundle: Vue Flow is dynamically isolated");
}
