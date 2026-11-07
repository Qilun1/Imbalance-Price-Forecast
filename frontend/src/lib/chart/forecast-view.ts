/**
 * The main forecast chart, kept plain on purpose: one pane, one price scale.
 *
 * - What happened before the forecast: a dark line with a soft fade under it.
 * - The forecast: a gold P50 line with the P10-P90 range as a light band around it.
 * - Nord Pool spot: a violet line, past and the day-ahead prices published for the forecast hours.
 * - "Show what happened" adds the realised price after the forecast time as a dark line.
 *
 * Risk and direction are not drawn here. The KPI row, the situations and the Next 10 h table carry them.
 *
 * The view opens on the chosen span of history plus the forecast. Dragging, a sideways swipe or the wheel
 * (zoom) moves through the rest of the history that was loaded.
 */
import {
  AreaSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  LineSeries,
  LineStyle,
  LineType,
  type UTCTimestamp,
  type WhitespaceData,
  type LineData,
} from "lightweight-charts";

import type { ActualPoint, Forecast } from "@/lib/api/client";
import { formatPriceAxis, fromUnixSeconds, toUnixSeconds } from "@/lib/format";
import type { Direction } from "@/lib/forecast";

import { type BandPoint, StepBand, TimeMarks } from "./primitives";
import { baseOptions, color, headingStyle, withAlpha } from "./theme";

export type ChartRow = {
  time: UTCTimestamp;
  p10: number | null;
  p50: number | null;
  p90: number | null;
  spot: number | null;
  actual: number | null;
  /** The realised price after the viewing time: hindsight, not known at that moment. */
  outcome: number | null;
  pUp: number | null;
  pDown: number | null;
  high: number | null;
  low: number | null;
  realised: Direction | null;
};

const EMPTY_ROW = {
  p10: null,
  p50: null,
  p90: null,
  spot: null,
  actual: null,
  outcome: null,
  pUp: null,
  pDown: null,
  high: null,
  low: null,
  realised: null,
};

export function buildRows(forecast: Forecast, history: readonly ActualPoint[], outcome: readonly ActualPoint[]): ChartRow[] {
  const rows = new Map<number, ChartRow>();
  const at = (iso: string) => {
    const time = toUnixSeconds(iso) as UTCTimestamp;
    const known = rows.get(time);
    if (known) return known;
    const row: ChartRow = { time, ...EMPTY_ROW };
    rows.set(time, row);
    return row;
  };
  for (const point of history) {
    const row = at(point.delivery_start_utc);
    row.actual = point.imbalance_price;
    row.spot = point.spot;
    row.realised = point.direction;
  }
  for (const step of forecast.steps) {
    const row = at(step.delivery_start_utc);
    row.p10 = step.p10;
    row.p50 = step.p50;
    row.p90 = step.p90;
    row.spot = step.spot ?? row.spot;
    row.pUp = step.p_up;
    row.pDown = step.p_down;
    row.high = step.p_spike_high;
    row.low = step.p_spike_low;
  }
  for (const point of outcome) {
    if (!rows.has(toUnixSeconds(point.delivery_start_utc))) continue;
    at(point.delivery_start_utc).outcome = point.imbalance_price;
  }
  return [...rows.values()].sort((a, b) => a.time - b.time);
}

type Point = LineData<UTCTimestamp> | WhitespaceData<UTCTimestamp>;

function series(rows: readonly ChartRow[], value: (row: ChartRow) => number | null): Point[] {
  return rows.map((row) => {
    const number = value(row);
    return number === null ? { time: row.time } : { time: row.time, value: number };
  });
}

function band(rows: readonly ChartRow[], upper: (row: ChartRow) => number | null, lower: (row: ChartRow) => number | null) {
  const points: BandPoint[] = [];
  for (const row of rows) {
    const [top, bottom] = [upper(row), lower(row)];
    if (top !== null && bottom !== null) points.push({ time: row.time, upper: top, lower: bottom });
  }
  return points;
}

export type ChartWindow = { start: string; end: string; selected: boolean };

export type ChartInput = {
  rows: readonly ChartRow[];
  origin: string;
  /** Kept for the callers; the spot +/- margin zone is no longer drawn. */
  margin: number;
  windows: readonly ChartWindow[];
  /** Hours of history in view when the chart opens, left of the forecast; null for all of it. */
  spanHours: number | null;
};

export class ForecastView {
  private readonly chart: IChartApi;
  private readonly actual: ISeriesApi<"Area">;
  private readonly spot: ISeriesApi<"Line">;
  private readonly p50: ISeriesApi<"Line">;
  private readonly outcome: ISeriesApi<"Line">;
  private readonly fan: StepBand;
  private readonly marks: TimeMarks;
  private rows = new Map<number, ChartRow>();
  private order: ChartRow[] = [];
  private cursor: number | null = null;

  constructor(host: HTMLElement, private readonly onCross: (row: ChartRow | null) => void) {
    const ink = color("ink");
    const gold = color("series-1");
    const base = baseOptions();

    this.chart = createChart(host, {
      ...base,
      grid: { vertLines: { visible: false }, horzLines: { color: withAlpha(color("chart-grid"), 0.6) } },
      rightPriceScale: { borderVisible: false, tickMarkDensity: 6, scaleMargins: { top: 0.12, bottom: 0.08 } },
      // Keeps the same hours in view when the panel changes width, so the forecast's end is never cut off.
      // minBarSpacing lets "All" fit months of quarter-hours into the panel.
      timeScale: { ...base.timeScale, borderVisible: false, lockVisibleTimeRangeOnResize: true, minBarSpacing: 0.01 },
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
      handleScale: {
        mouseWheel: true,
        pinch: true,
        axisPressedMouseMove: { time: true, price: false },
        axisDoubleClickReset: false,
      },
      crosshair: {
        ...base.crosshair,
        vertLine: { ...base.crosshair?.vertLine, style: LineStyle.Dashed, width: 1 },
      },
    });

    const line = {
      lineType: LineType.Simple,
      priceLineVisible: false,
      lastValueVisible: false,
      priceFormat: { type: "custom", formatter: (price: number) => formatPriceAxis(price), minMove: 0.01 } as const,
      crosshairMarkerRadius: 3,
    };

    // Added first, so it sits under the imbalance price lines.
    this.spot = this.chart.addSeries(LineSeries, { ...line, color: color("chart-spot"), lineWidth: 2 });
    this.actual = this.chart.addSeries(AreaSeries, {
      ...line,
      lineColor: ink,
      lineWidth: 2,
      topColor: withAlpha(ink, 0.1),
      bottomColor: withAlpha(ink, 0),
    });
    this.p50 = this.chart.addSeries(LineSeries, { ...line, color: gold, lineWidth: 2 });
    this.outcome = this.chart.addSeries(LineSeries, { ...line, color: ink, lineWidth: 2 });

    this.fan = new StepBand({ fill: withAlpha(color("chart-band"), 0.32), shape: "line" });
    this.p50.attachPrimitive(this.fan);

    this.marks = new TimeMarks(headingStyle().font);
    this.p50.attachPrimitive(this.marks);

    this.chart.subscribeCrosshairMove((event) => {
      const row = typeof event.time === "number" ? this.rows.get(event.time) : undefined;
      this.onCross(row ?? null);
    });
  }

  update({ rows, origin, windows, spanHours }: ChartInput): void {
    this.order = [...rows];
    this.rows = new Map(rows.map((row) => [row.time, row]));

    this.spot.setData(series(rows, (row) => row.spot));
    this.actual.setData(series(rows, (row) => row.actual));
    this.p50.setData(series(rows, (row) => row.p50));
    this.fan.setPoints(band(rows, (row) => row.p90, (row) => row.p10));
    this.outcome.setData(series(rows, (row) => row.outcome));

    // Only the situation picked on the right is shaded: overlapping windows stacked into a dark block.
    const warning = color("warning");
    const spans = windows
      .filter((window) => window.selected)
      .map((window) => ({
        from: toUnixSeconds(window.start) as UTCTimestamp,
        to: toUnixSeconds(window.end) as UTCTimestamp,
        fill: withAlpha(warning, 0.07),
      }));
    const axis = color("chart-axis");
    this.marks.set(spans, [
      { time: toUnixSeconds(origin) as UTCTimestamp, color: withAlpha(axis, 0.35), label: "Forecast", labelColor: axis },
    ]);

    // Every row is a point on the time scale (empty values are whitespace), so row positions are the
    // chart's logical indices, which hold even right after new data.
    const start = spanHours === null ? 0 : toUnixSeconds(origin) - spanHours * 3600;
    const from = Math.max(0, rows.findIndex((row) => row.time >= start));
    if (rows.length) this.chart.timeScale().setVisibleLogicalRange({ from, to: rows.length - 1 });
    this.cursor = null;
  }

  /** Keyboard twin of hovering: moves the crosshair one quarter-hour at a time. */
  moveCursor(direction: -1 | 1): void {
    if (!this.order.length) return;
    const firstForecast = this.order.findIndex((row) => row.p50 !== null);
    const start = this.cursor ?? (firstForecast < 0 ? 0 : firstForecast - direction);
    const next = Math.min(this.order.length - 1, Math.max(0, start + direction));
    const row = this.order[next];
    if (!row) return;
    this.cursor = next;
    this.chart.setCrosshairPosition(row.p50 ?? row.actual ?? 0, row.time, this.p50);
  }

  clearCursor(): void {
    this.cursor = null;
    this.chart.clearCrosshairPosition();
  }

  dispose(): void {
    this.chart.remove();
  }
}

export function rowTime(row: ChartRow): string {
  return fromUnixSeconds(row.time);
}
