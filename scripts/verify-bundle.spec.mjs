import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { assertFirstScreenExcludesVueFlow } from "./verify-bundle.mjs";

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
});
