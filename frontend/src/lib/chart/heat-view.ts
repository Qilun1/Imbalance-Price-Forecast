/**
 * Heat cost for the next 10 hours, € per MWh of heat on one scale: the electric boiler at each quarter-hour's
 * spot price against the chip boiler's flat cost. The gap between them is green where electric heat is cheaper
 * and yellow where the chip boiler is, so the cheaper source reads straight off the chart.
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
} from "lightweight-charts";

import { toUnixSeconds } from "@/lib/format";
import type { HeatCostPoint } from "@/lib/operator";

import { baseOptions, color, PRICE_FORMAT, withAlpha } from "./theme";

export class HeatView {
  private readonly chart: IChartApi;
  private readonly electric: ISeriesApi<"Baseline">;
  private readonly chips: ISeriesApi<"Line">;

  constructor(host: HTMLElement) {
    const cheaper = color("down");
    const dearer = color("warning");
    this.chart = createChart(host, baseOptions());
    this.electric = this.chart.addSeries(BaselineSeries, {
      topLineColor: dearer,
      topFillColor1: withAlpha(dearer, 0.3),
      topFillColor2: withAlpha(dearer, 0.3),
      bottomLineColor: cheaper,
      bottomFillColor1: withAlpha(cheaper, 0.3),
      bottomFillColor2: withAlpha(cheaper, 0.3),
      lineWidth: 2,
      lineType: LineType.WithSteps,
      priceLineVisible: false,
      lastValueVisible: false,
      priceFormat: PRICE_FORMAT,
    });
    this.chips = this.chart.addSeries(LineSeries, {
      color: color("ink"),
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
      priceFormat: PRICE_FORMAT,
    });
    this.chart.priceScale("right").applyOptions({ scaleMargins: { top: 0.15, bottom: 0.1 } });
  }

  update(points: readonly HeatCostPoint[]): void {
    const at = (point: HeatCostPoint) => toUnixSeconds(point.time) as UTCTimestamp;
    this.electric.applyOptions({ baseValue: { type: "price", price: points[0]?.chips ?? 0 } });
    this.electric.setData(points.map((point) => ({ time: at(point), value: point.electric })));
    this.chips.setData(points.map((point) => ({ time: at(point), value: point.chips })));
    this.chart.timeScale().fitContent();
  }

  dispose(): void {
    this.chart.remove();
  }
}
