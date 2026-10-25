function containsControlCharacter(value: string): boolean {
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    if (code <= 0x1f || code === 0x7f) {
      return true;
    }
  }
  return false;
}

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
    if (url.origin !== "https://app.invalid") {
      return fallback;
    }

    let decodedPath = url.pathname;
    for (let round = 0; round < 4; round += 1) {
      const decoded = decodeURIComponent(decodedPath);
      if (
        decoded.startsWith("//") ||
        decoded.includes("\\") ||
        containsControlCharacter(decoded)
      ) {
        return fallback;
      }
      if (decoded === decodedPath) {
        return `${url.pathname}${url.search}${url.hash}`;
      }
      const normalized = new URL(decoded, "https://app.invalid");
      if (normalized.origin !== "https://app.invalid") {
        return fallback;
      }
      decodedPath = normalized.pathname;
    }
    return fallback;
  } catch {
    return fallback;
  }
}
