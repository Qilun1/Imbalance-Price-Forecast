/** Forecast against what happened over a past period, at one lead time. */
import { createChart, type IChartApi, type ISeriesApi, LineSeries, LineStyle, LineType, type UTCTimestamp } from "lightweight-charts";

import type { HindsightPoint } from "@/lib/api/client";
import { toUnixSeconds } from "@/lib/format";

import { StepBand } from "./primitives";
import { baseOptions, color, PRICE_FORMAT, withAlpha } from "./theme";

const at = (point: HindsightPoint) => toUnixSeconds(point.delivery_start_utc) as UTCTimestamp;

export class HindsightView {
  private readonly chart: IChartApi;
  private readonly actual: ISeriesApi<"Line">;
  private readonly p50: ISeriesApi<"Line">;
  private readonly baseline: ISeriesApi<"Line">;
  private readonly fan: StepBand;

  constructor(host: HTMLElement) {
    const gold = color("series-1");
    this.chart = createChart(host, baseOptions());
    this.chart.timeScale().applyOptions({ minBarSpacing: 0.05 });
    const line = {
      lineType: LineType.WithSteps,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
      priceFormat: PRICE_FORMAT,
    };
    this.baseline = this.chart.addSeries(LineSeries, { ...line, color: color("ash"), lineWidth: 1, lineStyle: LineStyle.Dashed });
    this.p50 = this.chart.addSeries(LineSeries, { ...line, color: gold, lineWidth: 2 });
    this.actual = this.chart.addSeries(LineSeries, { ...line, color: color("ink"), lineWidth: 1 });
    this.fan = new StepBand({ fill: withAlpha(color("chart-band"), 0.38), edge: withAlpha(gold, 0.3) });
    this.p50.attachPrimitive(this.fan);
  }

  update(points: readonly HindsightPoint[]): void {
    const series = (value: (point: HindsightPoint) => number | null) =>
      points.map((point) => {
        const number = value(point);
        return number === null ? { time: at(point) } : { time: at(point), value: number };
      });
    this.baseline.setData(series((point) => point.baseline_p50));
    this.p50.setData(series((point) => point.p50));
    this.actual.setData(series((point) => point.actual));
    this.fan.setPoints(points.map((point) => ({ time: at(point), upper: point.p90, lower: point.p10 })));
    this.chart.timeScale().fitContent();
  }

  dispose(): void {
    this.chart.remove();
  }
}
