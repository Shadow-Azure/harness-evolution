#!/usr/bin/env node
// Style gate: design tokens remain the only source of literal colors in Vue components.

import path from "node:path";
import { pathToFileURL } from "node:url";
import { isMain } from "./is-main.mjs";

const COLOR_PATTERN = /#[0-9a-f]{3,8}\b|rgba?\(/i;

/**
 * Reject literal colors outside the token stylesheet.
 * @param {Array<{path: string, source: string}>} files Vue source files to audit.
 * @returns {void} Throws when a component contains a literal color.
 */
export function assertTokensAreOnlyColorSource(files) {
  for (const file of files) {
    if (file.path.endsWith("tokens.css")) continue;
    if (COLOR_PATTERN.test(file.source)) {
      throw new Error(`${file.path} contains a literal color; use tokens.css`);
    }
  }
}

if (isMain(import.meta.url)) {
  const { readdir, readFile } = await import("node:fs/promises");
  const sourceRoot = new URL("../apps/web/src", import.meta.url);
  const entries = await readdir(sourceRoot, { recursive: true, withFileTypes: true });
  const vueFiles = entries.filter((entry) => entry.isFile() && entry.name.endsWith(".vue"));
  const files = await Promise.all(
    vueFiles.map(async (entry) => {
      const filePath = path.join(entry.parentPath, entry.name);
      const source = await readFile(pathToFileURL(filePath), "utf8");
      return { path: filePath, source };
    })
  );
  assertTokensAreOnlyColorSource(files);
  console.log("verify-web-style: Vue components use token colors only");
}
