import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { assertTokensAreOnlyColorSource } from "./verify-web-style.mjs";

describe("verify-web-style", () => {
  it("accepts colors declared through design tokens", () => {
    assert.doesNotThrow(() =>
      assertTokensAreOnlyColorSource([
        { path: "apps/web/src/App.vue", source: ".item { color: var(--text-muted); }" }
      ])
    );
  });

  it("rejects literal colors in Vue components", () => {
    assert.throws(
      () =>
        assertTokensAreOnlyColorSource([
          { path: "apps/web/src/App.vue", source: ".item { color: rgba(255, 255, 255, 0.5); }" }
        ]),
      /tokens\.css/
    );
  });
});
