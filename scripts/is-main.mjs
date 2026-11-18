// Cross-platform CLI entry guard. pathToFileURL normalizes POSIX and Windows
// entry paths into the file:/// URL form that import.meta.url uses; realpath
// keeps the comparison stable when the entry is reached through a symlink.

import { realpathSync } from "node:fs";
import { pathToFileURL } from "node:url";

/**
 * Report whether the calling module is the process entry point.
 * @param {string} moduleUrl `import.meta.url` of the calling module.
 * @param {string | undefined} [entryPath] Entry path from `process.argv[1]`; defaults to the current process entry.
 * @returns {boolean} True when `entryPath` resolves to the same file URL as `moduleUrl`.
 */
export function isMain(moduleUrl, entryPath = process.argv[1]) {
  if (!entryPath) return false;
  try {
    return moduleUrl === pathToFileURL(realpathSync(entryPath)).href;
  } catch {
    return false;
  }
}
