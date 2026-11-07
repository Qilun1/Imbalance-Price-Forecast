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

export function withAlpha(hex: string, opacity: number): string {
  const channels = [1, 3, 5].map((start) => Number.parseInt(hex.slice(start, start + 2), 16));
  return `rgba(${channels.join(",")},${opacity})`;
}

function axisLabel(time: number): string {
  const iso = fromUnixSeconds(time);
  const isMidnight = utcHour(iso) === 0 && new Date(iso).getUTCMinutes() === 0;
  return isMidnight ? formatDate(iso) : formatClock(iso);
}

export const PRICE_FORMAT = { type: "custom", formatter: (price: number) => formatPrice(price), minMove: 0.01 } as const;

export function headingStyle(): HeadingStyle {
  return { font: `12px ${getComputedStyle(document.body).fontFamily}`, color: color("chart-axis"), background: color("surface") };
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
