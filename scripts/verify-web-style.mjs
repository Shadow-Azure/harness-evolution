#!/usr/bin/env node
// Style gate: design tokens remain the only source of literal colors in Vue components.

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

if (import.meta.url === `file://${process.argv[1]}`) {
  const { readdir, readFile } = await import("node:fs/promises");
  const sourceRoot = new URL("../apps/web/src", import.meta.url);
  const entries = await readdir(sourceRoot, { recursive: true, withFileTypes: true });
  const vueFiles = entries.filter((entry) => entry.isFile() && entry.name.endsWith(".vue"));
  const files = await Promise.all(
    vueFiles.map(async (entry) => {
      const path = `${entry.parentPath}/${entry.name}`;
      const source = await readFile(new URL(path, sourceRoot), "utf8");
      return { path, source };
    })
  );
  assertTokensAreOnlyColorSource(files);
  console.log("verify-web-style: Vue components use token colors only");
}
