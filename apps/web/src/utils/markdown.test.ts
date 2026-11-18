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

  it("preserves single line breaks", () => {
    const html = renderMarkdown("第一行\n第二行");

    expect(html).toContain("<br>");
  });

  it("linkifies bare URLs with the same hardening", () => {
    const html = renderMarkdown("证据：https://example.com/report");

    expect(html).toContain('href="https://example.com/report"');
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noopener noreferrer"');
  });

  it("keeps plain text as one paragraph", () => {
    const html = renderMarkdown("index read failed: 读取检索索引时抛出 ENOENT。");

    expect(html).toBe("<p>index read failed: 读取检索索引时抛出 ENOENT。</p>\n");
    expect(renderMarkdown("")).toBe("");
  });
});
