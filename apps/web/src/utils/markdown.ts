import MarkdownIt from "markdown-it";
import type Token from "markdown-it/lib/token.mjs";

const markdown = new MarkdownIt({
  breaks: true,
  html: false,
  linkify: true,
});

const defaultLinkOpen =
  markdown.renderer.rules.link_open ??
  ((tokens, index, options, _env, self) =>
    self.renderToken(tokens, index, options));

markdown.renderer.rules.link_open = (
  tokens: Token[],
  index: number,
  options,
  env,
  self,
) => {
  tokens[index]?.attrSet("target", "_blank");
  tokens[index]?.attrSet("rel", "noopener noreferrer");
  return defaultLinkOpen(tokens, index, options, env, self);
};

/**
 * Render trusted-format external attribution Markdown without raw HTML.
 * @param source External attribution reasoning text.
 * @returns Safe HTML accepted by the report panel.
 */
export function renderMarkdown(source: string): string {
  return markdown.render(source);
}
