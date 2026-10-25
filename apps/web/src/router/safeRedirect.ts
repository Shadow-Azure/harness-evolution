/**
 * Sanitize a login or password-change return target.
 * @param candidate User-provided route query value.
 * @param fallback In-app route used when the value is missing or unsafe.
 * @returns An app-relative path that cannot become an external redirect.
 */
export function safeRedirect(candidate: unknown, fallback = "/sessions"): string {
  if (typeof candidate !== "string" || !candidate.startsWith("/")) {
    return fallback;
  }
  if (candidate.startsWith("//") || candidate.includes("\\")) {
    return fallback;
  }
  try {
    const url = new URL(candidate, "https://app.invalid");
    return url.origin === "https://app.invalid"
      ? `${url.pathname}${url.search}${url.hash}`
      : fallback;
  } catch {
    return fallback;
  }
}
