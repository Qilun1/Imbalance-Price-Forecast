/**
 * The main forecast chart: two panes on one time axis, so the forecast line, the crosshair, dragging and
 * the history row hold for both.
 *
 * 1. Price, kept plain, one scale:
 *    - What happened before the forecast: a dark line with a soft fade under it.
 *    - The forecast: a gold P50 line with the P10-P90 prediction interval as a light band around it.
 *    - Nord Pool spot: a violet line, past and the day-ahead prices published for the forecast hours.
 *    - "Show what happened" adds the realised price after the forecast time as a dark line.
 * 2. Balancing direction, see `DirectionPane`. "Show what happened" carries its bars past the forecast line.
 *
 * A dark line at the forecast time, with a tag, marks where the facts end and the prediction starts.
 *
 * The view opens on the chosen span of history plus the forecast. Dragging, a sideways swipe or the wheel
 * (zoom) moves through the rest of the history that was loaded.
 */
import {
  AreaSeries,
  createChart,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  LineSeries,
  LineStyle,
  LineType,
  type UTCTimestamp,
  type WhitespaceData,
  type LineData,
} from "lightweight-charts";

import type { ActualPoint, Alert, Forecast } from "@/lib/api/client";
import { formatClock, formatPriceAxis, fromUnixSeconds, toUnixSeconds } from "@/lib/format";

import { DirectionPane, type DirectionReadout, type DirectionRow, HEADING_SHARE } from "./direction-pane";
import { type BandPoint, StepBand, TimeMarks } from "./primitives";
import { baseOptions, color, headingStyle, withAlpha } from "./theme";

const FORECAST_LINE_WIDTH = 2;

export type ChartRow = DirectionRow & {
  p10: number | null;
  p50: number | null;
  p90: number | null;
  spot: number | null;
  actual: number | null;
  /** The realised price after the viewing time: hindsight, not known at that moment. */
  outcome: number | null;
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
    const row = at(point.delivery_start_utc);
    row.outcome = point.imbalance_price;
    row.realised = point.direction;
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

function band(rows: readonly ChartRow[], upper: (row: ChartRow) => number | null, lower: (row: ChartRow) => number | null) {
  const points: BandPoint[] = [];
  for (const row of rows) {
    const [top, bottom] = [upper(row), lower(row)];
    if (top !== null && bottom !== null) points.push({ time: row.time, upper: top, lower: bottom });
  }
  return points;
}

export type ChartWindow = { start: string; end: string; selected: boolean; severity: Alert["severity"] };

/** A fixed price drawn across the chart with its name on the price axis, such as a plant's cost level. `tone` is a colour token. */
export type PriceLevel = { title: string; price: number; tone: string };

export type ChartInput = {
  rows: readonly ChartRow[];
  origin: string;
  windows: readonly ChartWindow[];
  /** A key figure's quarter-hours, shaded in grey with the crosshair on the first. */
  focus: { start: string; end: string } | null;
  /** Hours of history in view when the chart opens, left of the forecast; null for all of it. */
  spanHours: number | null;
  levels?: readonly PriceLevel[];
};

export class ForecastView {
  private readonly chart: IChartApi;
  private readonly actual: ISeriesApi<"Area">;
  private readonly spot: ISeriesApi<"Line">;
  private readonly p50: ISeriesApi<"Line">;
  private readonly outcome: ISeriesApi<"Line">;
  private readonly fan: StepBand;
  private readonly direction: DirectionPane;
  private levelLines: IPriceLine[] = [];
  /** One per pane; the first carries the forecast line's tag. */
  private readonly marks: readonly TimeMarks[];
  private rows = new Map<number, ChartRow>();
  private order: ChartRow[] = [];
  private cursor: number | null = null;
  /** Whether the crosshair is where a key figure put it, so letting go of the figure takes it away. */
  private pinned = false;
  private pinFrame = 0;

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

    this.direction = new DirectionPane(this.chart);

    // In the lower pane the line starts below the heading's strip, so it never crosses the figures there.
    const [priceMarks, directionMarks] = [new TimeMarks(`600 ${headingStyle().font}`), new TimeMarks("", true, HEADING_SHARE)];
    this.p50.attachPrimitive(priceMarks);
    this.direction.attach(directionMarks);
    this.marks = [priceMarks, directionMarks];

    this.chart.subscribeCrosshairMove((event) => {
      const row = typeof event.time === "number" ? this.rows.get(event.time) : undefined;
      this.onCross(row ?? null);
    });
  }

  update({ rows, origin, windows, focus, spanHours, levels = [] }: ChartInput): void {
    this.order = [...rows];
    this.rows = new Map(rows.map((row) => [row.time, row]));

    this.spot.setData(series(rows, (row) => row.spot));
    this.actual.setData(series(rows, (row) => row.actual));
    this.p50.setData(series(rows, (row) => row.p50));
    this.fan.setPoints(band(rows, (row) => row.p90, (row) => row.p10));
    this.outcome.setData(series(rows, (row) => row.outcome));

    this.direction.update(rows);

    for (const line of this.levelLines) this.p50.removePriceLine(line);
    this.levelLines = levels.map(({ title, price, tone }) =>
      this.p50.createPriceLine({ price, title, color: color(tone), lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true }),
    );

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
    // Grey, not a situation colour, so a key figure never reads as a warning.
    if (focus) {
      spans.push({ from: toUnixSeconds(focus.start) as UTCTimestamp, to: toUnixSeconds(focus.end) as UTCTimestamp, fill: withAlpha(color("ink"), 0.08) });
    }
    const made = { time: toUnixSeconds(origin) as UTCTimestamp, color: color("ink"), width: FORECAST_LINE_WIDTH };
    const tag = { label: `Forecast from ${formatClock(origin)} →`, labelColor: color("surface") };
    this.marks.forEach((marks, pane) => marks.set(spans, [pane === 0 ? { ...made, ...tag } : made]));

    // Every row is a point on the time scale (empty values are whitespace), so row positions are the
    // chart's logical indices, which hold even right after new data. The last index is the lower pane's
    // closing point. The view starts just after the span's first moment: a time label exactly on the left
    // edge would be cut in half.
    const start = spanHours === null ? 0 : toUnixSeconds(origin) - spanHours * 3600;
    const from = Math.max(0, rows.findIndex((row) => row.time > start));
    if (rows.length) this.chart.timeScale().setVisibleLogicalRange({ from, to: rows.length });
    this.cursor = null;
    // The arrow keys then carry on from the key figure.
    const focused = focus ? rows.findIndex((row) => row.time === toUnixSeconds(focus.start)) : -1;
    const row = rows[focused];
    cancelAnimationFrame(this.pinFrame);
    if (row) {
      this.cursor = focused;
      this.pinned = true;
      // A frame later, once the chart has drawn the new span: the crosshair keeps its place on screen, not
      // its time, so pinned before a change of span it would land on another quarter-hour.
      this.pinFrame = requestAnimationFrame(() => this.chart.setCrosshairPosition(row.p50 ?? row.actual ?? 0, row.time, this.p50));
    } else if (this.pinned) {
      // Only a crosshair a figure put there: one under the pointer stays through a data refresh.
      this.chart.clearCrosshairPosition();
      this.pinned = false;
    }
  }

  showDirection(readout: DirectionReadout): void {
    this.direction.show(readout);
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
    cancelAnimationFrame(this.pinFrame);
    this.chart.remove();
  }
}

export function rowTime(row: ChartRow): string {
  return fromUnixSeconds(row.time);
}
