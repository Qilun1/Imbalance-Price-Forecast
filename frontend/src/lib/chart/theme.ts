/** A canvas cannot use Tailwind classes, so charts read the same tokens as CSS variables at runtime. */
import {
  type ChartOptions,
  ColorType,
  CrosshairMode,
  type DeepPartial,
  type UTCTimestamp,
} from "lightweight-charts";

import { formatClock, formatDate, formatDateTime, formatPrice, fromUnixSeconds, utcHour } from "@/lib/format";

import type { HeadingStyle } from "./primitives";

export function color(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(`--color-${name}`).trim();
}

/** The production CSS is minified, so a token such as `#ffffff` can arrive here as `#fff`. */
function channels(hex: string): number[] {
  const digits = hex.slice(1);
  const full = digits.length === 3 ? [...digits].map((digit) => digit + digit).join("") : digits;
  return [0, 2, 4].map((start) => Number.parseInt(full.slice(start, start + 2), 16));
}

export function withAlpha(hex: string, opacity: number): string {
  return `rgba(${channels(hex).join(",")},${opacity})`;
}

/** A solid tint of `hex` on `background`. Unlike `withAlpha` it hides what is drawn behind it. */
export function tint(hex: string, opacity: number, background: string): string {
  const under = channels(background);
  const mixed = channels(hex).map((channel, index) => Math.round(channel * opacity + (under[index] ?? 0) * (1 - opacity)));
  return `rgb(${mixed.join(",")})`;
}

/** Midnight ticks get the date, the others the time. Every chart holds quarter-hours, so midnight is always there. */
function axisLabel(time: number): string {
  const iso = fromUnixSeconds(time);
  const isMidnight = utcHour(iso) === 0 && new Date(iso).getUTCMinutes() === 0;
  return isMidnight ? formatDate(iso) : formatClock(iso);
}

export const PRICE_FORMAT = { type: "custom", formatter: (price: number) => formatPrice(price), minMove: 0.01 } as const;

export function headingStyle(): HeadingStyle {
  return {
    font: `12px ${getComputedStyle(document.body).fontFamily}`,
    color: color("chart-axis"),
    noteColor: color("ink"),
    background: color("surface"),
  };
}

export function baseOptions(): DeepPartial<ChartOptions> {
  const surface = color("surface");
  const hairline = color("hairline");
  const axis = color("chart-axis");
  const crosshair = color("chart-crosshair");
  const grid = color("chart-grid");
  return {
    autoSize: true,
    layout: {
      background: { type: ColorType.Solid, color: surface },
      textColor: axis,
      fontFamily: getComputedStyle(document.body).fontFamily,
      fontSize: 12,
      attributionLogo: false, // the licence's notice and link are in ShortcutsDialog, on every screen
      panes: { separatorColor: hairline, separatorHoverColor: hairline, enableResize: false },
    },
    grid: { vertLines: { color: grid }, horzLines: { color: grid } },
    crosshair: {
      mode: CrosshairMode.Normal,
      vertLine: { color: crosshair, labelBackgroundColor: crosshair },
      horzLine: { visible: false, labelVisible: false },
    },
    rightPriceScale: { borderColor: hairline },
    timeScale: {
      borderColor: hairline,
      timeVisible: true,
      secondsVisible: false,
      fixLeftEdge: true,
      fixRightEdge: true,
      tickMarkFormatter: (time: UTCTimestamp) => axisLabel(time),
    },
    localization: {
      locale: "en-GB",
      timeFormatter: (time: UTCTimestamp) => formatDateTime(fromUnixSeconds(time)),
    },
    handleScale: { mouseWheel: false, pinch: true, axisPressedMouseMove: false, axisDoubleClickReset: false },
    handleScroll: { mouseWheel: false, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
  };
}
