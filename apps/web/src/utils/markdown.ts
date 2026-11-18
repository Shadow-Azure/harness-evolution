import MarkdownIt from "markdown-it";
import type Token from "markdown-it/lib/token.mjs";

function createMarkdown({ images }: { images: boolean }): MarkdownIt {
  const instance = new MarkdownIt({
    breaks: true,
    html: false,
    linkify: true,
  });
  if (!images) {
    instance.renderer.rules.image = (tokens, index) =>
      instance.utils.escapeHtml(tokens[index]?.content ?? "");
  }

  const defaultLinkOpen =
    instance.renderer.rules.link_open ??
    ((tokens, index, options, _env, self) =>
      self.renderToken(tokens, index, options));

  instance.renderer.rules.link_open = (
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
  return instance;
}

const markdown = createMarkdown({ images: true });
const markdownWithoutImages = createMarkdown({ images: false });

/**
 * Render trusted-format Markdown without raw HTML.
 * Used by attribution reasoning and the bad-case description body.
 * @param source Markdown text from a trusted report or server template.
 * @param options Rendering options; `images: false` drops Markdown image nodes.
 * @returns Safe HTML accepted by the report and description panels.
 */
export function renderMarkdown(
  source: string,
  options: { images?: boolean } = {},
): string {
  const renderer = options.images === false ? markdownWithoutImages : markdown;
  return renderer.render(source);
}
