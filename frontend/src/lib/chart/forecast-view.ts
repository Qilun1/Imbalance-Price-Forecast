/**
 * The main forecast chart: three panes on one time axis, each with its own single scale.
 *
 * 1. Price: last 24 h of actuals, the P10-P90 fan, P50, spot and the spot +/- 50 zone.
 * 2. Exceptional price risk: high upward, low downward.
 * 3. Balancing direction: up upward, down downward.
 *
 * Values hold for a whole quarter-hour, so every series is stepped. History sits in the lower panes at
 * full height: there it is what happened, not a probability.
 */
import {
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

import type { ActualPoint, Forecast } from "@/lib/api/client";
import { formatDate, formatPercent, fromUnixSeconds, toUnixSeconds, utcHour } from "@/lib/format";
import type { Direction } from "@/lib/forecast";

import { type BandPoint, PaneHeading, StepBand, TimeMarks } from "./primitives";
import { baseOptions, color, headingStyle, PRICE_FORMAT, withAlpha } from "./theme";

const QUARTER_HOUR = 900;
const WHOLE_SCALE = { priceRange: { minValue: -1, maxValue: 1 } };
/** Share of a lower pane kept clear of data for its heading. */
const HEADING_SHARE = 0.3;

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

/** Stepped lines end where their last value starts, so a closing point shows the final quarter-hour. */
function closed(rows: readonly ChartRow[], value: (row: ChartRow) => number | null): Point[] {
  const points = series(rows, value);
  const last = rows.findLast((row) => value(row) !== null);
  const end = rows.at(-1);
  if (!last || !end) return points;
  return [...points, { time: (end.time + QUARTER_HOUR) as UTCTimestamp, value: value(last) as number }];
}

function band(rows: readonly ChartRow[], upper: (row: ChartRow) => number | null, lower: (row: ChartRow) => number | null) {
  const points: BandPoint[] = [];
  for (const row of rows) {
    const [top, bottom] = [upper(row), lower(row)];
    if (top !== null && bottom !== null) points.push({ time: row.time, upper: top, lower: bottom });
  }
  const last = points.at(-1);
  if (last) points.push({ ...last, time: (last.time + QUARTER_HOUR) as UTCTimestamp });
  return points;
}

function realisedSign(direction: Direction | null): number | null {
  if (direction === null) return null;
  return { up: 1, down: -1, none: 0 }[direction];
}

export type ChartWindow = { start: string; end: string; selected: boolean };

export type ChartInput = {
  rows: readonly ChartRow[];
  origin: string;
  margin: number;
  windows: readonly ChartWindow[];
};

export class ForecastView {
  private readonly chart: IChartApi;
  private readonly actual: ISeriesApi<"Line">;
  private readonly p50: ISeriesApi<"Line">;
  private readonly spot: ISeriesApi<"Line">;
  private readonly outcome: ISeriesApi<"Line">;
  private readonly riskHigh: ISeriesApi<"Baseline">;
  private readonly riskLow: ISeriesApi<"Baseline">;
  private readonly riskRealised: ISeriesApi<"Baseline">;
  private readonly direction: ISeriesApi<"Baseline">;
  private readonly directionRealised: ISeriesApi<"Baseline">;
  private readonly fan: StepBand;
  private readonly zone: StepBand;
  private readonly marks: TimeMarks[];
  private rows = new Map<number, ChartRow>();
  private order: ChartRow[] = [];
  private cursor: number | null = null;

  constructor(host: HTMLElement, private readonly onCross: (row: ChartRow | null) => void) {
    const ink = color("ink");
    const gold = color("series-1");
    const stone = color("stone");
    const up = color("up");
    const down = color("down");
    const hairline = color("hairline");

    this.chart = createChart(host, baseOptions());
    const line = { lineType: LineType.WithSteps, priceLineVisible: false, lastValueVisible: false };
    const price = { ...line, priceFormat: PRICE_FORMAT, crosshairMarkerVisible: false };

    this.spot = this.chart.addSeries(LineSeries, { ...price, color: stone, lineWidth: 1, lineStyle: LineStyle.Dashed });
    this.actual = this.chart.addSeries(LineSeries, { ...price, color: ink, lineWidth: 1 });
    this.p50 = this.chart.addSeries(LineSeries, { ...price, color: gold, lineWidth: 2 });
    this.outcome = this.chart.addSeries(LineSeries, { ...price, color: ink, lineWidth: 2 });

    this.zone = new StepBand({ fill: withAlpha(color("chart-zone"), 0.06), edge: withAlpha(color("chart-zone"), 0.18) });
    this.fan = new StepBand({ fill: withAlpha(color("chart-band"), 0.38), edge: withAlpha(gold, 0.45) });
    this.spot.attachPrimitive(this.zone);
    this.p50.attachPrimitive(this.fan);

    const signal = (top: string, bottom: string, fill: number, pane: number) =>
      this.chart.addSeries(
        BaselineSeries,
        {
          ...line,
          baseValue: { type: "price", price: 0 },
          topLineColor: top,
          topFillColor1: withAlpha(top, fill),
          topFillColor2: withAlpha(top, fill),
          bottomLineColor: bottom,
          bottomFillColor1: withAlpha(bottom, fill),
          bottomFillColor2: withAlpha(bottom, fill),
          lineWidth: 1,
          crosshairMarkerVisible: false,
          autoscaleInfoProvider: () => WHOLE_SCALE,
          priceFormat: { type: "custom", formatter: (value: number) => formatPercent(Math.abs(value)), minMove: 0.01 },
        },
        pane,
      );

    this.riskRealised = signal(up, down, 0.22, 1);
    this.riskHigh = signal(up, down, 0.5, 1);
    this.riskLow = signal(up, down, 0.5, 1);
    this.directionRealised = signal(up, down, 0.22, 2);
    this.direction = signal(up, down, 0.5, 2);

    for (const baseline of [this.riskHigh, this.direction]) {
      baseline.createPriceLine({ price: 0, color: hairline, lineWidth: 1, lineStyle: LineStyle.Solid, axisLabelVisible: false });
    }

    for (const pane of [1, 2]) {
      this.chart.priceScale("right", pane).applyOptions({ tickMarkDensity: 1.2, scaleMargins: { top: HEADING_SHARE, bottom: 0.06 } });
    }

    const panes = this.chart.panes();
    panes[0]?.setStretchFactor(2.8);
    panes[1]?.setStretchFactor(1);
    panes[2]?.setStretchFactor(1);
    const heading = headingStyle();
    this.riskHigh.attachPrimitive(new PaneHeading("Exceptional price risk: high above, low below", HEADING_SHARE, heading));
    this.direction.attachPrimitive(new PaneHeading("Balancing direction: up above, down below", HEADING_SHARE, heading));

    this.marks = [this.p50, this.riskHigh, this.direction].map((owner, pane) => {
      const marks = new TimeMarks(pane === 0 ? heading.font : "");
      owner.attachPrimitive(marks);
      return marks;
    });

    this.chart.subscribeCrosshairMove((event) => {
      const row = typeof event.time === "number" ? this.rows.get(event.time) : undefined;
      this.onCross(row ?? null);
    });
  }

  update({ rows, origin, margin, windows }: ChartInput): void {
    this.order = [...rows];
    this.rows = new Map(rows.map((row) => [row.time, row]));

    this.spot.setData(closed(rows, (row) => row.spot));
    this.zone.setPoints(
      band(
        rows,
        (row) => (row.spot === null ? null : row.spot + margin),
        (row) => (row.spot === null ? null : row.spot - margin),
      ),
    );
    this.actual.setData(series(rows, (row) => row.actual));
    this.p50.setData(closed(rows, (row) => row.p50));
    this.fan.setPoints(band(rows, (row) => row.p90, (row) => row.p10));
    this.outcome.setData(series(rows, (row) => row.outcome));

    this.riskHigh.setData(closed(rows, (row) => row.high));
    this.riskLow.setData(closed(rows, (row) => (row.low === null ? null : -row.low)));
    this.riskRealised.setData(
      series(rows, (row) => {
        if (row.actual === null || row.spot === null) return null;
        if (row.actual > row.spot + margin) return 1;
        return row.actual < row.spot - margin ? -1 : 0;
      }),
    );
    this.direction.setData(closed(rows, (row) => (row.pUp === null || row.pDown === null ? null : row.pUp - row.pDown)));
    this.directionRealised.setData(series(rows, (row) => realisedSign(row.realised)));

    const warning = color("warning");
    const spans = windows.map((window) => ({
      from: toUnixSeconds(window.start) as UTCTimestamp,
      to: toUnixSeconds(window.end) as UTCTimestamp,
      fill: withAlpha(warning, window.selected ? 0.16 : 0.05),
    }));
    const axis = color("chart-axis");
    const crosshair = color("chart-crosshair");
    const days = rows
      .filter((row) => {
        const iso = fromUnixSeconds(row.time);
        return utcHour(iso) === 0 && new Date(iso).getUTCMinutes() === 0;
      })
      .map((row) => ({ time: row.time, color: withAlpha(axis, 0.3), label: formatDate(fromUnixSeconds(row.time)), labelColor: axis }));
    const made = { time: toUnixSeconds(origin) as UTCTimestamp, color: crosshair, label: "Forecast made", labelColor: crosshair };
    const lines = [made, ...days];
    this.marks[0]?.set(spans, lines);
    const unlabelled = lines.map(({ time, color: tone }) => ({ time, color: tone }));
    for (const marks of this.marks.slice(1)) marks.set(spans, unlabelled);

    this.chart.timeScale().fitContent();
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
    this.chart.setCrosshairPosition(row.spot ?? 0, row.time, this.spot);
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
