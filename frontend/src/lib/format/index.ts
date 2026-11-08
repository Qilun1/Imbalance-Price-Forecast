/**
 * Every number, date and time on screen goes through this module. Components never round or format.
 * The API speaks UTC and so does the dashboard, so the clock change on 25 Oct needs no special handling.
 */
import { TZDate } from "@date-fns/tz";
import { format } from "date-fns";

export const NO_VALUE = "–";
const MINUS = "−";
const HOUR_MS = 3_600_000;

type Maybe = number | null | undefined;

const isNumber = (value: Maybe): value is number => typeof value === "number" && Number.isFinite(value);

function grouped(value: number, digits: number): string {
  return new Intl.NumberFormat("en-GB", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
}

/** Rounded magnitude with a true minus sign, so a negative that rounds to zero loses its sign. */
function signedText(value: number, digits: number, plus: string): string {
  const text = grouped(Math.abs(value), digits);
  const isZero = Number(Math.abs(value).toFixed(digits)) === 0;
  if (isZero) return text;
  return `${value < 0 ? MINUS : plus}${text}`;
}

// ---------- prices ----------

export const PRICE_UNIT = "€/MWh";

export function formatPrice(value: Maybe): string {
  return isNumber(value) ? signedText(value, 1, "") : NO_VALUE;
}

/** A price with the euro sign in front, as "€63.9"; `plus` signs positive values, as "+€5.0". */
export function formatEuro(value: Maybe, { plus = false, digits = 1 } = {}): string {
  if (!isNumber(value)) return NO_VALUE;
  const text = grouped(Math.abs(value), digits);
  if (Number(Math.abs(value).toFixed(digits)) === 0) return `€${text}`;
  return `${value < 0 ? MINUS : plus ? "+" : ""}€${text}`;
}

/** Whole euros, for chart axes where decimals only add noise. */
export function formatPriceAxis(value: Maybe): string {
  return isNumber(value) ? signedText(value, 0, "") : NO_VALUE;
}

export function formatPriceWithUnit(value: Maybe): string {
  return isNumber(value) ? `${formatPrice(value)} ${PRICE_UNIT}` : NO_VALUE;
}

export function formatSignedPrice(value: Maybe): string {
  return isNumber(value) ? signedText(value, 1, "+") : NO_VALUE;
}

export function formatPriceRange(low: Maybe, high: Maybe): string {
  return `${formatPrice(low)} to ${formatPrice(high)}`;
}

// ---------- probabilities ----------

export function formatPercent(probability: Maybe): string {
  if (!isNumber(probability)) return NO_VALUE;
  const percent = probability * 100;
  if (percent > 0 && percent < 1) return "<1%";
  return `${grouped(percent, 0)}%`;
}

/** A change in probability, in percentage points. */
export function formatPoints(change: Maybe): string {
  return isNumber(change) ? `${signedText(change * 100, 0, "+")} pp` : NO_VALUE;
}

// ---------- money, power and time spans ----------

export function formatSignedEuro(value: Maybe): string {
  if (!isNumber(value)) return NO_VALUE;
  if (Math.round(Math.abs(value)) === 0) return "€0";
  return `${value < 0 ? MINUS : "+"}€${grouped(Math.abs(value), 0)}`;
}

export function formatMegawatts(value: Maybe): string {
  return isNumber(value) ? `${grouped(value, value % 1 === 0 ? 0 : 1)} MW` : NO_VALUE;
}

/** A count of quarter-hours as hours, as "3.5 h" or "3.25 h". */
export function formatQuarterHours(quarters: Maybe): string {
  if (!isNumber(quarters)) return NO_VALUE;
  return `${grouped(quarters / 4, quarters % 4 === 0 ? 0 : quarters % 2 === 0 ? 1 : 2)} h`;
}

export function formatMinutes(minutes: Maybe): string {
  if (!isNumber(minutes)) return NO_VALUE;
  const whole = Math.round(minutes);
  if (whole < 60) return `${whole} min`;
  const rest = whole % 60;
  return rest ? `${Math.floor(whole / 60)} h ${rest} min` : `${Math.floor(whole / 60)} h`;
}

// ---------- scores ----------

export function formatScore(value: Maybe, digits = 2): string {
  return isNumber(value) ? grouped(value, digits) : NO_VALUE;
}

/** For scores where lower is better: "34% better". */
export function formatBetter(value: Maybe, reference: Maybe): string {
  if (!isNumber(value) || !isNumber(reference) || reference === 0) return NO_VALUE;
  const change = value / reference - 1;
  if (Math.abs(change) < 0.005) return "No better";
  return `${grouped(Math.abs(change) * 100, 0)}% ${change < 0 ? "better" : "worse"}`;
}

export function formatCount(value: Maybe): string {
  return isNumber(value) ? grouped(value, 0) : NO_VALUE;
}

// ---------- API time ----------

/** The exact form the API and the organiser's files use: YYYY-MM-DDTHH:MM:SSZ. */
export function toApiTime(moment: Date | number | string): string {
  return new Date(moment).toISOString().replace(/\.\d{3}Z$/, "Z");
}

export function addHours(iso: string, hours: number): string {
  return toApiTime(new Date(iso).getTime() + hours * HOUR_MS);
}

export function addMinutes(iso: string, minutes: number): string {
  return toApiTime(new Date(iso).getTime() + minutes * 60_000);
}

export function floorToHour(iso: string): string {
  return toApiTime(Math.floor(new Date(iso).getTime() / HOUR_MS) * HOUR_MS);
}

export function hoursBetween(from: string, to: string): number {
  return (new Date(to).getTime() - new Date(from).getTime()) / HOUR_MS;
}

export function toUnixSeconds(iso: string): number {
  return Math.floor(new Date(iso).getTime() / 1000);
}

export function fromUnixSeconds(seconds: number): string {
  return toApiTime(seconds * 1000);
}

// ---------- time on screen ----------

const inUtc = (iso: string) => new TZDate(iso, "UTC");

export function formatClock(iso: string): string {
  return format(inUtc(iso), "HH:mm");
}

export function formatDate(iso: string): string {
  return format(inUtc(iso), "EEE d MMM");
}

export function formatWeekday(iso: string): string {
  return format(inUtc(iso), "EEE");
}

/** For tight spaces such as a chart readout. */
export function formatShortDateTime(iso: string): string {
  return format(inUtc(iso), "d MMM HH:mm");
}

export function formatDateTime(iso: string): string {
  return format(inUtc(iso), "EEE d MMM HH:mm");
}

/** The exact API form, for hover text. */
export function formatUtc(iso: string): string {
  return toApiTime(iso);
}

/** For text read on its own, where the zone must be named. */
export function formatClockUtc(iso: string): string {
  return `${formatClock(iso)} UTC`;
}

export function formatDateTimeUtc(iso: string): string {
  return `${formatDateTime(iso)} UTC`;
}

function endsOnSameDay(start: string, end: string): boolean {
  return format(inUtc(start), "yyyy-MM-dd") === format(inUtc(addMinutes(end, -1)), "yyyy-MM-dd");
}

/** A time window, naming the days only when it crosses midnight. The end is exclusive. */
export function formatWindow(start: string, end: string): string {
  if (endsOnSameDay(start, end)) return `${formatClock(start)}–${formatClock(end)}`;
  const short = (iso: string) => format(inUtc(iso), "EEE HH:mm");
  return `${short(start)}–${short(end)}`;
}

/** A window with its day always named, for lists that span several days. */
export function formatWindowWithDay(start: string, end: string): string {
  const window = formatWindow(start, end);
  return endsOnSameDay(start, end) ? `${formatWeekday(start)} ${window}` : window;
}

export function formatDayRange(start: string, end: string): string {
  return `${formatDate(start)} to ${formatDate(addMinutes(end, -1))}`;
}

export function utcHour(iso: string): number {
  return inUtc(iso).getHours();
}

/** Midnight of the UTC date of `iso`, as a plain Date for the calendar control. */
export function toCalendarDate(iso: string): Date {
  const when = inUtc(iso);
  return new Date(when.getFullYear(), when.getMonth(), when.getDate());
}

/** The moment of an hour on a date picked from the calendar control, read as UTC. */
export function fromUtcDate(date: Date, hour: number): string {
  return toApiTime(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate(), hour));
}
