/**
 * Format a compact duration for cards and overview metadata.
 * @param seconds Non-negative duration in seconds.
 * @returns Human-readable duration such as `9m` or `2h`.
 */
export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.max(0, Math.round(seconds))}s`;
  if (seconds < 3_600) return `${Math.round(seconds / 60)}m`;
  const hours = Math.floor(seconds / 3_600);
  const minutes = Math.floor((seconds % 3_600) / 60);
  return minutes ? `${hours}h${minutes}m` : `${hours}h`;
}

/**
 * Format token counts using compact engineering units.
 * @param tokens Non-negative token count.
 * @returns Compact token text such as `12k` or `1.3M`.
 */
export function formatTokens(tokens: number): string {
  if (tokens >= 1_000_000) {
    return `${(tokens / 1_000_000).toFixed(1)}M`;
  }
  if (tokens >= 1_000) {
    return `${Math.round(tokens / 1_000)}k`;
  }
  return String(tokens);
}

/**
 * Format a per-hundred-message density for the prototype progress rows.
 * @param value Density value whose full scale is three.
 * @returns One-decimal value with its denominator.
 */
export function formatDensity(value: number): string {
  return `${Math.max(0, value).toFixed(1)}/百消息`;
}

/**
 * Format a session start timestamp for the browser.
 * @param value ISO timestamp returned by the API.
 * @returns Localized date and time.
 */
export function formatStartedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

/**
 * Convert a per-100 density into a clamped progress percentage.
 * @param value Density value whose full scale is three.
 * @returns Percentage from zero through one hundred.
 */
export function densityWidth(value: number): string {
  return `${Math.min(100, Math.max(0, (value / 3) * 100))}%`;
}
