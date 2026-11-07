/**
 * How one window looked in each forecast that covered it: the average P50 above and the peak risk below.
 * Two panes, because a price and a probability do not share a scale.
 */
import {
  BaselineSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  LineSeries,
  LineType,
  type UTCTimestamp,
} from "lightweight-charts";

import { formatPercent, toUnixSeconds } from "@/lib/format";
import type { RevisionPoint } from "@/lib/forecast";

import { PaneHeading } from "./primitives";
import { baseOptions, color, headingStyle, withAlpha } from "./theme";

/** Share of each pane kept clear of data for its heading. */
const HEADING_SHARE = 0.24;

export class RevisionView {
  private readonly chart: IChartApi;
  private readonly p50: ISeriesApi<"Line">;
  private readonly high: ISeriesApi<"Baseline">;
  private readonly low: ISeriesApi<"Baseline">;

  constructor(host: HTMLElement) {
    const up = color("up");
    const down = color("down");
    this.chart = createChart(host, baseOptions());
    this.chart.timeScale().applyOptions({ fixLeftEdge: false, fixRightEdge: false });
    this.p50 = this.chart.addSeries(LineSeries, {
      color: color("series-1"),
      lineWidth: 2,
      lineType: LineType.Simple,
      pointMarkersVisible: true,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    const risk = (tone: string) =>
      this.chart.addSeries(
        BaselineSeries,
        {
          baseValue: { type: "price", price: 0 },
          topLineColor: tone,
          topFillColor1: withAlpha(tone, 0.4),
          topFillColor2: withAlpha(tone, 0.4),
          bottomLineColor: tone,
          bottomFillColor1: withAlpha(tone, 0.4),
          bottomFillColor2: withAlpha(tone, 0.4),
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
          autoscaleInfoProvider: () => ({ priceRange: { minValue: -1, maxValue: 1 } }),
          priceFormat: { type: "custom", formatter: (value: number) => formatPercent(Math.abs(value)), minMove: 0.01 },
        },
        1,
      );
    this.high = risk(up);
    this.low = risk(down);
    const panes = this.chart.panes();
    panes[0]?.setStretchFactor(1.4);
    panes[1]?.setStretchFactor(1);
    for (const pane of [0, 1]) {
      this.chart.priceScale("right", pane).applyOptions({ scaleMargins: { top: HEADING_SHARE, bottom: 0.06 } });
    }
    const heading = headingStyle();
    this.p50.attachPrimitive(new PaneHeading("Average P50 for this window", HEADING_SHARE, heading));
    this.high.attachPrimitive(new PaneHeading("Peak risk: high above, low below", HEADING_SHARE, heading));
  }

  update(points: readonly RevisionPoint[]): void {
    const at = (point: RevisionPoint) => toUnixSeconds(point.origin) as UTCTimestamp;
    this.p50.setData(points.map((point) => ({ time: at(point), value: point.p50 })));
    this.high.setData(points.map((point) => ({ time: at(point), value: point.p_spike_high })));
    this.low.setData(points.map((point) => ({ time: at(point), value: -point.p_spike_low })));
    this.chart.timeScale().fitContent();
  }

  dispose(): void {
    this.chart.remove();
  }
}
