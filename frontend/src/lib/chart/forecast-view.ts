/**
 * The main forecast chart: two panes on one time axis, so the forecast line, the crosshair, dragging and
 * the history row hold for both.
 *
 * 1. Price, kept plain, one scale:
 *    - What happened before the forecast: a dark line with a soft fade under it.
 *    - The forecast: a gold P50 line with the P10-P90 prediction interval as a light band around it.
 *    - Nord Pool spot: a violet line, past and the day-ahead prices published for the forecast hours.
 *    - "Show what happened" adds the realised price after the forecast time as a dark line.
 * 2. Balancing direction: up above the middle line, down below it.
 *
 * After the forecast line the lower pane shows the forecast's chances, the same numbers as the Next 10 h
 * table. Before it a pale block at full height is what happened, not a probability. These values hold for
 * a whole quarter-hour, so those series are stepped.
 *
 * The view opens on the chosen span of history plus the forecast. Dragging, a sideways swipe or the wheel
 * (zoom) moves through the rest of the history that was loaded.
 */
import {
  AreaSeries,
  BaselineSeries,
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

import type { ActualPoint, Alert, Forecast } from "@/lib/api/client";
import { formatPriceAxis, fromUnixSeconds, toUnixSeconds } from "@/lib/format";
import type { Direction } from "@/lib/forecast";

import { type BandPoint, PaneHeading, StepBand, TimeMarks } from "./primitives";
import { baseOptions, color, headingStyle, withAlpha } from "./theme";

const QUARTER_HOUR = 900;
const PRICE_PANE_STRETCH = 2;
const WHOLE_SCALE = { priceRange: { minValue: -1, maxValue: 1 } };
/** Share of the lower pane kept clear of data for its heading. */
const HEADING_SHARE = 0.14;
const HAPPENED_FILL = 0.22;
const FORECAST_FILL = 0.5;

const DIRECTION_SIGN: Record<Direction, number> = { up: 1, none: 0, down: -1 };

/**
 * Whole percent either side of the middle line. Blank past 100 %: the heading's strip stretches the scale
 * beyond it, and no chance is that large.
 */
function axisPercent(value: number): string {
  const percent = Math.abs(value) * 100;
  return percent > 100.5 ? "" : `${Math.round(percent)}%`;
}

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
  }
  for (const point of outcome) {
    if (!rows.has(toUnixSeconds(point.delivery_start_utc))) continue;
    at(point.delivery_start_utc).outcome = point.imbalance_price;
  }
  return [...rows.values()].sort((a, b) => a.time - b.time);
}

type Point = LineData<UTCTimestamp> | WhitespaceData<UTCTimestamp>;
type Value = (row: ChartRow) => number | null;

function series(rows: readonly ChartRow[], value: Value): Point[] {
  return rows.map((row) => {
    const number = value(row);
    return number === null ? { time: row.time } : { time: row.time, value: number };
  });
}

/** Stepped lines end where their last value starts, so a closing point shows the final quarter-hour. */
function closed(rows: readonly ChartRow[], value: Value): Point[] {
  const points = series(rows, value);
  const last = rows.findLast((row) => value(row) !== null);
  const end = rows.at(-1);
  if (!last || !end) return points;
  return [...points, { time: (end.time + QUARTER_HOUR) as UTCTimestamp, value: value(last) as number }];
}

const below = (value: number | null) => (value === null ? null : -value);

function band(rows: readonly ChartRow[], upper: (row: ChartRow) => number | null, lower: (row: ChartRow) => number | null) {
  const points: BandPoint[] = [];
  for (const row of rows) {
    const [top, bottom] = [upper(row), lower(row)];
    if (top !== null && bottom !== null) points.push({ time: row.time, upper: top, lower: bottom });
  }
  return points;
}

export type ChartWindow = { start: string; end: string; selected: boolean; severity: Alert["severity"] };

export type ChartInput = {
  rows: readonly ChartRow[];
  origin: string;
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
  private readonly directionHappened: ISeriesApi<"Baseline">;
  private readonly up: ISeriesApi<"Baseline">;
  private readonly down: ISeriesApi<"Baseline">;
  private readonly fan: StepBand;
  /** One per pane; the first carries the "Forecast" label. */
  private readonly marks: readonly TimeMarks[];
  private rows = new Map<number, ChartRow>();
  private order: ChartRow[] = [];
  private cursor: number | null = null;

  constructor(host: HTMLElement, private readonly onCross: (row: ChartRow | null) => void) {
    const ink = color("ink");
    const gold = color("series-1");
    const upColor = color("up");
    const downColor = color("down");
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

    const signal = (fill: number) =>
      this.chart.addSeries(
        BaselineSeries,
        {
          lineType: LineType.WithSteps,
          priceLineVisible: false,
          lastValueVisible: false,
          baseValue: { type: "price", price: 0 },
          topLineColor: upColor,
          topFillColor1: withAlpha(upColor, fill),
          topFillColor2: withAlpha(upColor, fill),
          bottomLineColor: downColor,
          bottomFillColor1: withAlpha(downColor, fill),
          bottomFillColor2: withAlpha(downColor, fill),
          lineWidth: 1,
          crosshairMarkerVisible: false,
          autoscaleInfoProvider: () => WHOLE_SCALE,
          priceFormat: { type: "custom", formatter: axisPercent, minMove: 0.01 },
        },
        1,
      );

    // What happened goes first, so the forecast is drawn over it.
    this.directionHappened = signal(HAPPENED_FILL);
    this.up = signal(FORECAST_FILL);
    this.down = signal(FORECAST_FILL);

    this.up.createPriceLine({ price: 0, color: color("hairline"), lineWidth: 1, lineStyle: LineStyle.Solid, axisLabelVisible: false });
    this.chart.priceScale("right", 1).applyOptions({ borderVisible: false, tickMarkDensity: 2, scaleMargins: { top: HEADING_SHARE, bottom: 0.06 } });
    this.chart.panes().forEach((pane, index) => pane.setStretchFactor(index === 0 ? PRICE_PANE_STRETCH : 1));

    const heading = headingStyle();
    this.up.attachPrimitive(new PaneHeading("Balancing direction: up above, down below (pale: what happened)", HEADING_SHARE, heading));

    // Attached after the heading, so the forecast line runs through its strip.
    this.marks = [new TimeMarks(heading.font), new TimeMarks("", true)];
    [this.p50, this.up].forEach((owner, pane) => {
      const marks = this.marks[pane];
      if (marks) owner.attachPrimitive(marks);
    });

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

    this.directionHappened.setData(series(rows, (row) => (row.realised === null ? null : DIRECTION_SIGN[row.realised])));
    this.up.setData(closed(rows, (row) => row.pUp));
    this.down.setData(closed(rows, (row) => below(row.pDown)));

    // Only the situation picked on the right is shaded: overlapping windows stacked into a dark block.
    // Red for Review and yellow for Watch, like the badges. Both stay see-through: the prediction interval
    // is drawn underneath, and it is what the shaded window is about.
    const spans = windows
      .filter((window) => window.selected)
      .map((window) => ({
        from: toUnixSeconds(window.start) as UTCTimestamp,
        to: toUnixSeconds(window.end) as UTCTimestamp,
        fill: window.severity === "review" ? withAlpha(color("error-text"), 0.12) : withAlpha(color("warning-bg"), 0.4),
      }));
    const axis = color("chart-axis");
    const time = toUnixSeconds(origin) as UTCTimestamp;
    const made = { time, color: withAlpha(axis, 0.35) };
    this.marks.forEach((marks, pane) => marks.set(spans, [pane === 0 ? { ...made, label: "Forecast", labelColor: axis } : made]));

    // Every row is a point on the time scale (empty values are whitespace), so row positions are the
    // chart's logical indices, which hold even right after new data. The last index is the lower pane's
    // closing point. The view starts just after the span's first moment: a time label exactly on the left
    // edge would be cut in half.
    const start = spanHours === null ? 0 : toUnixSeconds(origin) - spanHours * 3600;
    const from = Math.max(0, rows.findIndex((row) => row.time > start));
    if (rows.length) this.chart.timeScale().setVisibleLogicalRange({ from, to: rows.length });
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
    // The chart reports only the pointer's moves, so the readout is told about this one directly.
    this.onCross(row);
  }

  clearCursor(): void {
    this.cursor = null;
    this.chart.clearCrosshairPosition();
    this.onCross(null);
  }

  dispose(): void {
    this.chart.remove();
  }
}

export function rowTime(row: ChartRow): string {
  return fromUnixSeconds(row.time);
}
