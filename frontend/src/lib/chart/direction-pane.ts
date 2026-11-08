/**
 * The balancing direction pane under a price chart, on the same time axis, shared by the Now and Hindsight
 * charts. Up sits above the middle line, down below it.
 *
 * - What happened: a solid bar from the middle line to the pane's edge. Bars are `Blocks`, not a series: a
 *   line joins across empty rows, which would draw a bar over quarter-hours not yet published.
 * - The forecast's chances: a see-through fill from the middle line, the same numbers as the Next 10 h table,
 *   so a bar shows through it in full. Over a bar of its own colour the fill cannot be seen, so there its
 *   edge is drawn white and still marks the chance. Chances hold for a whole quarter-hour, so they are
 *   stepped, and each step takes the colour of its own quarter-hour.
 *
 * With `happened: "edge"` (Hindsight, where every quarter-hour has both) what happened is a thin strip past
 * 100 % instead, up above and down below, so the chances are never broken by bars. There solid colour means
 * only what happened: the chances' edge is a muted tint, not the strips' solid colour, or it would read as
 * a third strip.
 *
 * A row after the pane's heading names the values under the crosshair, its swatches the legend for both.
 */
import {
  type BaselineData,
  BaselineSeries,
  type IChartApi,
  type ISeriesApi,
  type ISeriesPrimitive,
  LineSeries,
  LineType,
  type Time,
  type UTCTimestamp,
  type WhitespaceData,
} from "lightweight-charts";

import { type Direction, directionLabel } from "@/lib/forecast";
import { formatClock, formatEuro, formatPercent, fromUnixSeconds } from "@/lib/format";

import { Blocks, PaneHeading } from "./primitives";
import { color, headingStyle, tint, withAlpha } from "./theme";

const QUARTER_HOUR = 900;
const PRICE_PANE_STRETCH = 2;
/** Share of the pane kept clear of data for its heading, enough to leave air between the two graphs. */
export const HEADING_SHARE = 0.24;
const HAPPENED_BARS = { up: { upper: 1, lower: 0 }, down: { upper: 0, lower: -1 } };
/** The edge strips sit past 100 %, with a gap, so a chance of 100 % still shows its line. */
const HAPPENED_EDGE = { up: { upper: 1.16, lower: 1.05 }, down: { upper: -1.05, lower: -1.16 } };
const SCALE = { bars: 1, edge: 1.16 };
const CHANCE_FILL = 0.35;
/** The chances' edge next to the edge strips: darker than the fill, clearly lighter than a strip. */
const CHANCE_EDGE_TINT = 0.55;
const CHANCE_LINE_WIDTH = 2;
const WIDEST_CHANCE = "100%";

/**
 * Whole percent either side of the middle line. Blank past 100 %: the heading's strip stretches the scale
 * beyond it, and no chance is that large.
 */
function axisPercent(value: number): string {
  const percent = Math.abs(value) * 100;
  return percent > 100.5 ? "" : `${Math.round(percent)}%`;
}

export type DirectionRow = {
  time: UTCTimestamp;
  pUp: number | null;
  pDown: number | null;
  /** The direction that happened. */
  realised: Direction | null;
};

export type HappenedRun = { from: UTCTimestamp; to: UTCTimestamp; direction: "up" | "down" };

/**
 * What happened, as runs of one direction, each ending where the next row starts. An unknown quarter-hour
 * ends a run, so nothing is drawn over the ones not yet published. A quarter-hour with no dominating
 * direction ends one too, and has no bar.
 */
export function happenedRuns(rows: readonly DirectionRow[]): HappenedRun[] {
  const runs: HappenedRun[] = [];
  let open: HappenedRun | null = null;
  rows.forEach((row, index) => {
    const { realised } = row;
    if (realised === null || realised === "none") {
      open = null;
      return;
    }
    const to = rows[index + 1]?.time ?? ((row.time + QUARTER_HOUR) as UTCTimestamp);
    if (open?.direction === realised) {
      open.to = to;
      return;
    }
    open = { from: row.time, to, direction: realised };
    runs.push(open);
  });
  return runs;
}

/** The row after the pane's heading. `happened` is left out until a direction is known. */
export type DirectionReadout = { up: string; down: string; happened: { direction: Direction; text: string } | null };

/**
 * `shown` gives the chances. `known` is a row with a direction, which may be another quarter-hour, so the
 * text names its own time. `price` is the imbalance price that direction decided.
 */
export function readDirection(shown: DirectionRow | null, known: DirectionRow | null, price: number | null): DirectionReadout {
  const direction = known?.realised;
  const decided = known && direction ? `${formatClock(fromUnixSeconds(known.time))} ${directionLabel(direction)}` : null;
  return {
    up: formatPercent(shown?.pUp),
    down: formatPercent(shown?.pDown),
    happened: direction && decided ? { direction, text: price === null ? decided : `${decided}, decided at ${formatEuro(price)}` } : null,
  };
}

type Value = (row: DirectionRow) => number | null;
type Edge = (row: DirectionRow) => Pick<BaselineData<UTCTimestamp>, "topLineColor" | "bottomLineColor">;

/** Stepped lines end where their last value starts, so a closing point shows the final quarter-hour. */
function closedSteps(rows: readonly DirectionRow[], value: Value, edge: Edge): (BaselineData<UTCTimestamp> | WhitespaceData<UTCTimestamp>)[] {
  const points = rows.map((row) => {
    const number = value(row);
    return number === null ? { time: row.time } : { time: row.time, value: number, ...edge(row) };
  });
  const last = rows.findLast((row) => value(row) !== null);
  const end = rows.at(-1);
  if (!last || !end) return points;
  return [...points, { time: (end.time + QUARTER_HOUR) as UTCTimestamp, value: value(last) as number, ...edge(last) }];
}

const below = (value: number | null) => (value === null ? null : -value);

export type HappenedStyle = "bars" | "edge";

export class DirectionPane {
  /** The middle line. It has a point for every row, so the bars keep a scale even when no chances came. */
  private readonly middle: ISeriesApi<"Line">;
  private readonly up: ISeriesApi<"Baseline">;
  private readonly down: ISeriesApi<"Baseline">;
  private readonly happened = new Blocks();
  private readonly heading: PaneHeading;
  private readonly solid: Record<HappenedRun["direction"], string>;
  /** How the see-through chances look on the pane's background, for the swatches. */
  private readonly pale: Record<HappenedRun["direction"], string>;
  private readonly surface: string;

  constructor(
    chart: IChartApi,
    private readonly style: HappenedStyle = "bars",
  ) {
    this.solid = { up: color("up"), down: color("down") };
    this.surface = color("surface");
    this.pale = { up: tint(this.solid.up, CHANCE_FILL, this.surface), down: tint(this.solid.down, CHANCE_FILL, this.surface) };
    const fill = { up: withAlpha(this.solid.up, CHANCE_FILL), down: withAlpha(this.solid.down, CHANCE_FILL) };
    const edge =
      style === "edge"
        ? { up: tint(this.solid.up, CHANCE_EDGE_TINT, this.surface), down: tint(this.solid.down, CHANCE_EDGE_TINT, this.surface) }
        : this.solid;
    const percent = { type: "custom", formatter: axisPercent, minMove: 0.01 } as const;
    const whole = { priceRange: { minValue: -SCALE[style], maxValue: SCALE[style] } };

    this.middle = chart.addSeries(
      LineSeries,
      {
        color: color("hairline"),
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
        autoscaleInfoProvider: () => whole,
        priceFormat: percent,
      },
      1,
    );

    const chance = () =>
      chart.addSeries(
        BaselineSeries,
        {
          lineType: LineType.WithSteps,
          priceLineVisible: false,
          lastValueVisible: false,
          baseValue: { type: "price", price: 0 },
          topLineColor: edge.up,
          topFillColor1: fill.up,
          topFillColor2: fill.up,
          bottomLineColor: edge.down,
          bottomFillColor1: fill.down,
          bottomFillColor2: fill.down,
          lineWidth: CHANCE_LINE_WIDTH,
          crosshairMarkerVisible: false,
          autoscaleInfoProvider: () => whole,
          priceFormat: percent,
        },
        1,
      );
    this.up = chance();
    this.down = chance();
    this.middle.attachPrimitive(this.happened);

    chart.priceScale("right", 1).applyOptions({ borderVisible: false, tickMarkDensity: 2, scaleMargins: { top: HEADING_SHARE, bottom: 0.06 } });
    chart.panes().forEach((pane, index) => pane.setStretchFactor(index === 0 ? PRICE_PANE_STRETCH : 1));

    this.heading = new PaneHeading("Balancing direction", HEADING_SHARE, headingStyle());
    this.middle.attachPrimitive(this.heading);
  }

  /** For marks that belong in this pane. */
  attach(primitive: ISeriesPrimitive<Time>): void {
    this.middle.attachPrimitive(primitive);
  }

  update(rows: readonly DirectionRow[]): void {
    // The closing point gives the last quarter-hour's bar its right edge.
    const end = rows.at(-1);
    const close = end ? [{ time: (end.time + QUARTER_HOUR) as UTCTimestamp, value: 0 }] : [];
    this.middle.setData([...rows.map(({ time }) => ({ time, value: 0 })), ...close]);
    const place = this.style === "edge" ? HAPPENED_EDGE : HAPPENED_BARS;
    this.happened.set(happenedRuns(rows).map(({ from, to, direction }) => ({ from, to, ...place[direction], fill: this.solid[direction] })));
    // Over a bar of the same direction the chance's own colour would vanish, so its edge turns white there.
    // Edge strips never lie under a chance, so the edge keeps its muted tint.
    const bars = this.style === "bars";
    this.up.setData(closedSteps(rows, (row) => row.pUp, (row) => (bars && row.realised === "up" ? { topLineColor: this.surface } : {})));
    this.down.setData(closedSteps(rows, (row) => below(row.pDown), (row) => (bars && row.realised === "down" ? { bottomLineColor: this.surface } : {})));
  }

  /** The swatches explain the pane: pale for the chances, solid for the bars of what happened. */
  show({ up, down, happened }: DirectionReadout): void {
    const fact = happened && {
      label: "Happened",
      value: happened.text,
      swatch: happened.direction === "none" ? undefined : this.solid[happened.direction],
    };
    this.heading.setItems([
      { swatch: this.pale.up, label: "Up", value: up, reserve: WIDEST_CHANCE },
      { swatch: this.pale.down, label: "Down", value: down, reserve: WIDEST_CHANCE },
      ...(fact ? [fact] : []),
    ]);
  }
}
