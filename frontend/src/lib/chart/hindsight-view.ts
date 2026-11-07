/**
 * Forecast against what happened over a past period, at one lead time. The same series, names and colours
 * as the Now chart, so one legend reads both:
 *
 * - Actual: the realised imbalance price, a dark line with a soft fade under it.
 * - Spot: Nord Pool spot, a violet line.
 * - Forecast: the P50 made `lead` hours ahead, gold, with the P10-P90 likely range as a light band.
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
} from "lightweight-charts";

import { formatPriceAxis } from "@/lib/format";

import { StepBand } from "./primitives";
import { baseOptions, color, withAlpha } from "./theme";

export type HindsightRow = {
  time: UTCTimestamp;
  actual: number | null;
  spot: number | null;
  p10: number;
  p50: number;
  p90: number;
};

export class HindsightView {
  private readonly chart: IChartApi;
  private readonly actual: ISeriesApi<"Area">;
  private readonly spot: ISeriesApi<"Line">;
  private readonly p50: ISeriesApi<"Line">;
  private readonly fan: StepBand;
  private byTime = new Map<number, HindsightRow>();

  constructor(host: HTMLElement, private readonly onCross: (row: HindsightRow | null) => void) {
    const ink = color("ink");
    const base = baseOptions();
    this.chart = createChart(host, {
      ...base,
      grid: { vertLines: { visible: false }, horzLines: { color: withAlpha(color("chart-grid"), 0.6) } },
      rightPriceScale: { borderVisible: false, tickMarkDensity: 6, scaleMargins: { top: 0.1, bottom: 0.08 } },
      timeScale: { ...base.timeScale, borderVisible: false, lockVisibleTimeRangeOnResize: true, minBarSpacing: 0.01 },
      crosshair: { ...base.crosshair, vertLine: { ...base.crosshair?.vertLine, style: LineStyle.Dashed, width: 1 } },
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
      handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: { time: true, price: false }, axisDoubleClickReset: false },
    });
    const line = {
      lineType: LineType.Simple,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerRadius: 3,
      priceFormat: { type: "custom", formatter: (price: number) => formatPriceAxis(price), minMove: 0.01 } as const,
    };
    // Same order as the Now chart: spot under the imbalance prices.
    this.spot = this.chart.addSeries(LineSeries, { ...line, color: color("chart-spot"), lineWidth: 2 });
    this.actual = this.chart.addSeries(AreaSeries, {
      ...line,
      lineColor: ink,
      lineWidth: 1,
      topColor: withAlpha(ink, 0.1),
      bottomColor: withAlpha(ink, 0),
    });
    this.p50 = this.chart.addSeries(LineSeries, { ...line, color: color("series-1"), lineWidth: 2 });
    this.fan = new StepBand({ fill: withAlpha(color("chart-band"), 0.32), shape: "line" });
    this.p50.attachPrimitive(this.fan);
    this.chart.subscribeCrosshairMove((event) => {
      this.onCross(typeof event.time === "number" ? (this.byTime.get(event.time) ?? null) : null);
    });
  }

  update(rows: readonly HindsightRow[]): void {
    this.byTime = new Map(rows.map((row) => [row.time, row]));
    const series = (value: (row: HindsightRow) => number | null) =>
      rows.map((row) => {
        const number = value(row);
        return number === null ? { time: row.time } : { time: row.time, value: number };
      });
    this.spot.setData(series((row) => row.spot));
    this.actual.setData(series((row) => row.actual));
    this.p50.setData(series((row) => row.p50));
    this.fan.setPoints(rows.map((row) => ({ time: row.time, upper: row.p90, lower: row.p10 })));
    this.chart.timeScale().fitContent();
  }

  dispose(): void {
    this.chart.remove();
  }
}
