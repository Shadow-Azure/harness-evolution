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
 * Render trusted-format Markdown without raw HTML.
 * Used by attribution reasoning and the bad-case description body.
 * @param source Markdown text from a trusted external report.
 * @returns Safe HTML accepted by the report and description panels.
 */
export function renderMarkdown(source: string): string {
  return markdown.render(source);
}
