/** One-click ranges offered next to the bad-case time window. */
export type RangePresetId = "7" | "30" | "6m";

/** A labelled shortcut offered next to the bad-case time window. */
export interface RangePreset {
  id: RangePresetId;
  label: string;
}

/** Closed date range written into the two native date inputs. */
export interface RangePresetRange {
  from: string;
  to: string;
}

/** Presets shown in step 1, in display order. */
export const RANGE_PRESETS: readonly RangePreset[] = [
  { id: "7", label: "近 7 天" },
  { id: "30", label: "近 30 天" },
  { id: "6m", label: "近半年" },
];

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

/**
 * Format a local `Date` as an ISO calendar day without a UTC shift.
 * @param date Local calendar date.
 * @returns `YYYY-MM-DD` in the viewer's timezone.
 */
export function localIsoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/**
 * Parse a calendar day at local noon so DST transitions cannot move it.
 * @param iso `YYYY-MM-DD` calendar day.
 * @returns A local `Date`, or `null` when the input is not a real date.
 */
function parseIsoDate(iso: string): Date | null {
  const match = ISO_DATE.exec(iso);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const date = new Date(year, month - 1, day, 12, 0, 0, 0);
  if (
    date.getFullYear() !== year ||
    date.getMonth() !== month - 1 ||
    date.getDate() !== day
  ) {
    return null;
  }
  return date;
}

/**
 * Add calendar days to a `YYYY-MM-DD` value.
 * @param iso Starting calendar day.
 * @param days Signed number of days to add.
 * @returns The resulting `YYYY-MM-DD` value.
 * @throws When `iso` is not a real `YYYY-MM-DD` date.
 */
export function addCalendarDays(iso: string, days: number): string {
  const date = parseIsoDate(iso);
  if (!date) throw new Error(`invalid calendar day: ${iso}`);
  date.setDate(date.getDate() + days);
  return localIsoDate(date);
}

/**
 * Add calendar months, clamping to the target month's last day.
 * @param iso Starting calendar day.
 * @param months Signed number of months to add.
 * @returns The resulting `YYYY-MM-DD` value, clamped at month end.
 * @throws When `iso` is not a real `YYYY-MM-DD` date.
 */
export function addCalendarMonths(iso: string, months: number): string {
  const date = parseIsoDate(iso);
  if (!date) throw new Error(`invalid calendar day: ${iso}`);
  const day = date.getDate();
  date.setDate(1);
  date.setMonth(date.getMonth() + months);
  const lastDay = new Date(
    date.getFullYear(),
    date.getMonth() + 1,
    0,
  ).getDate();
  date.setDate(Math.min(day, lastDay));
  return localIsoDate(date);
}

/**
 * Compute the concrete closed range for one preset.
 * @param id Preset identifier.
 * @param todayIso The viewer's current local calendar day.
 * @returns Inclusive `from`/`to` dates.
 */
export function presetRange(
  id: RangePresetId,
  todayIso: string,
): RangePresetRange {
  if (id === "6m") {
    return { from: addCalendarMonths(todayIso, -6), to: todayIso };
  }
  const days = Number(id);
  return { from: addCalendarDays(todayIso, -(days - 1)), to: todayIso };
}

/**
 * Resolve which preset exactly matches the current closed range.
 * @param from Current start date, or an empty string.
 * @param to Current end date, or an empty string.
 * @param todayIso The viewer's current local calendar day.
 * @returns The matching preset id, or `null` for a custom range.
 */
export function activePresetId(
  from: string,
  to: string,
  todayIso: string,
): RangePresetId | null {
  if (!from || !to) return null;
  for (const preset of RANGE_PRESETS) {
    const range = presetRange(preset.id, todayIso);
    if (range.from === from && range.to === to) return preset.id;
  }
  return null;
}
