import { describe, expect, it } from "vitest";

import { renderMarkdown } from "./markdown";

describe("attribution Markdown", () => {
  it("renders lists, code blocks and hardened external links", () => {
    const html = renderMarkdown(
      "1. first\n2. second\n\n```ts\nconst value = 1\n```\n\n[source](https://example.com)",
    );

    expect(html).toContain("<ol>");
    expect(html).toContain("<pre><code");
    expect(html).toContain('href="https://example.com"');
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noopener noreferrer"');
  });

  it("does not render raw HTML", () => {
    const html = renderMarkdown(
      '<img src=x onerror="alert(1)"><script>alert(2)</script>',
    );

    expect(html).not.toContain("<img");
    expect(html).not.toContain("<script");
  });
});
