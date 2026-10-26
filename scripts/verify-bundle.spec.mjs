import assert from "node:assert/strict";
import { randomBytes } from "node:crypto";
import { describe, it } from "node:test";

import {
  ENTRY_GZIP_MAX_BYTES,
  ENTRY_RAW_MAX_BYTES,
  REQUIRED_VENDOR_CHUNKS,
  VENDOR_RAW_MAX_BYTES,
  assertBundleBudgets,
  assertFirstScreenExcludesVueFlow,
} from "./verify-bundle.mjs";

describe("verify-bundle", () => {
  it("requires a dynamic Vue Flow chunk outside the entry", () => {
    const manifest = {
      "index.html": {
        dynamicImports: ["src/pages/evolution/Index.vue", "vendor-vue-flow"],
        file: "assets/index.js",
        isEntry: true,
        name: "index"
      },
      "src/pages/evolution/Index.vue": {
        imports: ["vendor-vue-flow"],
        file: "assets/EvolutionPage.js",
        isDynamicEntry: true,
        name: "Index"
      },
      "vendor-vue-flow": {
        file: "assets/vendor-vue-flow.js",
        isDynamicEntry: true,
        name: "vendor-vue-flow"
      }
    };

    assertFirstScreenExcludesVueFlow(manifest, "import './assets/EvolutionPage.js'");
  });

  it("allows Vite preload metadata that names the isolated dynamic vendor chunk", () => {
    const manifest = {
      "_vendor-vue-flow.js": {
        file: "assets/vendor-vue-flow.js",
        name: "vendor-vue-flow"
      },
      "index.html": {
        dynamicImports: ["src/pages/evolution/Index.vue"],
        file: "assets/index.js",
        isEntry: true,
        name: "index"
      },
      "src/pages/evolution/Index.vue": {
        imports: ["_vendor-vue-flow.js"],
        file: "assets/EvolutionPage.js",
        isDynamicEntry: true,
        name: "Index"
      }
    };

    assertFirstScreenExcludesVueFlow(
      manifest,
      'const deps=["assets/EvolutionPage.js","assets/vendor-vue-flow.js"]'
    );
  });

  it("fails when Vue Flow is reachable from the synchronous entry", () => {
    const manifest = {
      "index.html": {
        imports: ["vendor-vue-flow"],
        file: "assets/index.js",
        isEntry: true,
        name: "index"
      },
      "vendor-vue-flow": { dynamicImports: [], file: "assets/vendor-vue-flow.js", name: "vendor-vue-flow" }
    };

    assert.throws(
      () => assertFirstScreenExcludesVueFlow(manifest, "import './assets/vendor-vue-flow.js'"),
      /first screen/i
    );
  });

  it("enforces entry and vendor size budgets", () => {
    const manifest = {
      "index.html": { file: "assets/index.js", isEntry: true, name: "index" },
      "_vendor-vue.js": { file: "assets/vendor-vue.js", name: "vendor-vue" },
      "_vendor-element-plus.js": {
        file: "assets/vendor-element-plus.js",
        name: "vendor-element-plus",
      },
      "_vendor-vue-flow.js": {
        file: "assets/vendor-vue-flow.js",
        name: "vendor-vue-flow",
      },
    };
    const assets = {
      "assets/index.js": Buffer.alloc(ENTRY_RAW_MAX_BYTES, "a"),
      "assets/vendor-vue.js": Buffer.alloc(VENDOR_RAW_MAX_BYTES, "v"),
      "assets/vendor-element-plus.js": Buffer.alloc(1, "e"),
      "assets/vendor-vue-flow.js": Buffer.alloc(1, "f"),
    };
    const measured = assertBundleBudgets(manifest, (file) => assets[file]);
    assert.equal(measured.entry.raw, ENTRY_RAW_MAX_BYTES);
    assert.ok(measured.entry.gzip <= ENTRY_GZIP_MAX_BYTES);
    assert.equal(measured.vendors["_vendor-vue.js"], VENDOR_RAW_MAX_BYTES);
    for (const required of REQUIRED_VENDOR_CHUNKS) {
      assert.ok(
        Object.keys(measured.vendors).some((key) => key.includes(required)),
        `${required} was not measured`,
      );
    }

    assert.throws(
      () =>
        assertBundleBudgets(manifest, (file) =>
          file === "assets/index.js"
            ? Buffer.alloc(ENTRY_RAW_MAX_BYTES + 1, "a")
            : Buffer.alloc(1, "b"),
        ),
      /entry bundle/i,
    );
    assert.throws(
      () =>
        assertBundleBudgets(manifest, (file) =>
          file === "assets/vendor-vue.js"
            ? Buffer.alloc(VENDOR_RAW_MAX_BYTES + 1, "v")
            : Buffer.alloc(1, "a"),
        ),
      /vendor chunk/i,
    );
  });

  it("enforces the entry gzip budget independently of raw size", () => {
    const manifest = {
      "index.html": { file: "assets/index.js", isEntry: true, name: "index" },
      "_vendor-vue.js": { file: "assets/vendor-vue.js", name: "vendor-vue" },
      "_vendor-element-plus.js": {
        file: "assets/vendor-element-plus.js",
        name: "vendor-element-plus",
      },
      "_vendor-vue-flow.js": {
        file: "assets/vendor-vue-flow.js",
        name: "vendor-vue-flow",
      },
    };
    const incompressible = randomBytes(150 * 1024);
    assert.throws(
      () =>
        assertBundleBudgets(manifest, (file) =>
          file === "assets/index.js" ? incompressible : Buffer.alloc(1),
        ),
      /gzip exceeds/i,
    );
  });

  it("fails when a required manual vendor chunk is missing", () => {
    const manifest = {
      "index.html": { file: "assets/index.js", isEntry: true, name: "index" },
      "_vendor-vue.js": { file: "assets/vendor-vue.js", name: "vendor-vue" },
      "_vendor-element-plus.js": {
        file: "assets/vendor-element-plus.js",
        name: "vendor-element-plus",
      },
      framework: { file: "assets/framework.js", name: "framework" },
    };
    assert.throws(
      () =>
        assertBundleBudgets(manifest, (file) =>
          file === "assets/framework.js"
            ? Buffer.alloc(500 * 1024)
            : Buffer.alloc(1),
        ),
      /required vendor chunk missing: vendor-vue-flow/,
    );
  });
});
