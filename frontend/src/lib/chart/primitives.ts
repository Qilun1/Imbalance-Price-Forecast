/**
 * Small drawing additions Lightweight Charts has no series for.
 *
 * StepBand fills between two values that hold for a whole quarter-hour: the P10-P90 fan and the spot +/- 50
 * zone. Blocks draws solid boxes that stay apart across a gap, as a series would join them. TimeMarks shades
 * time windows and draws a vertical line at the forecast time, in any pane. PaneHeading gives a pane a title
 * in its own strip, clear of the data.
 */
import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type {
  AutoscaleInfo,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  SeriesType,
  Time,
  UTCTimestamp,
} from "lightweight-charts";

type Attached = SeriesAttachedParameter<Time, SeriesType>;

function paneView(paint: (target: CanvasRenderingTarget2D) => void): IPrimitivePaneView {
  const renderer: IPrimitivePaneRenderer = { draw: () => undefined, drawBackground: paint };
  return { zOrder: () => "bottom", renderer: () => renderer };
}

export type BandPoint = { time: UTCTimestamp; upper: number; lower: number };

export class StepBand implements ISeriesPrimitive<Time> {
  private host: Attached | null = null;
  private points: BandPoint[] = [];
  private readonly views: readonly IPrimitivePaneView[];

  /** `shape: "line"` joins the points straight, to sit under plain (not stepped) lines. No `edge`, no outline. */
  constructor(private readonly style: { fill: string; edge?: string; shape?: "step" | "line" }) {
    this.views = [paneView((target) => this.paint(target))];
  }

  attached(host: Attached): void {
    this.host = host;
  }

  detached(): void {
    this.host = null;
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }

  /** Points must be in time order. The last point closes the final quarter-hour. */
  setPoints(points: BandPoint[]): void {
    this.points = points;
    this.host?.requestUpdate();
  }

  autoscaleInfo(): AutoscaleInfo | null {
    if (!this.points.length) return null;
    return {
      priceRange: {
        minValue: Math.min(...this.points.map((point) => point.lower)),
        maxValue: Math.max(...this.points.map((point) => point.upper)),
      },
    };
  }

  private paint(target: CanvasRenderingTarget2D): void {
    const host = this.host;
    if (!host || this.points.length < 2) return;
    const scale = host.chart.timeScale();
    const coordinates = this.points.flatMap((point) => {
      const x = scale.timeToCoordinate(point.time);
      const upper = host.series.priceToCoordinate(point.upper);
      const lower = host.series.priceToCoordinate(point.lower);
      return x === null || upper === null || lower === null ? [] : [{ x, upper, lower }];
    });
    if (coordinates.length < 2) return;

    target.useMediaCoordinateSpace(({ context }) => {
      if (this.style.shape === "line") {
        context.beginPath();
        for (const point of coordinates) context.lineTo(point.x, point.upper);
        for (const point of coordinates.toReversed()) context.lineTo(point.x, point.lower);
        context.closePath();
        context.fillStyle = this.style.fill;
        context.fill();
        return;
      }
      const pairs = coordinates.slice(0, -1).map((point, index) => [point, coordinates[index + 1] ?? point] as const);
      context.beginPath();
      for (const [left, right] of pairs) {
        context.lineTo(left.x, left.upper);
        context.lineTo(right.x, left.upper);
      }
      for (const [left, right] of pairs.toReversed()) {
        context.lineTo(right.x, left.lower);
        context.lineTo(left.x, left.lower);
      }
      context.closePath();
      context.fillStyle = this.style.fill;
      context.fill();
      if (!this.style.edge) return;

      context.strokeStyle = this.style.edge;
      context.lineWidth = 1;
      for (const edge of ["upper", "lower"] as const) {
        context.beginPath();
        for (const [left, right] of pairs) {
          context.lineTo(left.x, left[edge]);
          context.lineTo(right.x, left[edge]);
        }
        context.stroke();
      }
    });
  }
}

export type Block = { from: UTCTimestamp; to: UTCTimestamp; upper: number; lower: number; fill: string };

export class Blocks implements ISeriesPrimitive<Time> {
  private host: Attached | null = null;
  private blocks: readonly Block[] = [];
  private readonly views: readonly IPrimitivePaneView[] = [paneView((target) => this.paint(target))];

  attached(host: Attached): void {
    this.host = host;
  }

  detached(): void {
    this.host = null;
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }

  set(blocks: readonly Block[]): void {
    this.blocks = blocks;
    this.host?.requestUpdate();
  }

  private paint(target: CanvasRenderingTarget2D): void {
    const host = this.host;
    if (!host) return;
    const scale = host.chart.timeScale();
    target.useMediaCoordinateSpace(({ context }) => {
      for (const block of this.blocks) {
        const from = scale.timeToCoordinate(block.from);
        const to = scale.timeToCoordinate(block.to);
        const upper = host.series.priceToCoordinate(block.upper);
        const lower = host.series.priceToCoordinate(block.lower);
        if (from === null || to === null || upper === null || lower === null) continue;
        context.fillStyle = block.fill;
        context.fillRect(from, upper, to - from, lower - upper);
      }
    });
  }
}

export type HeadingStyle = { font: string; color: string; noteColor: string; background: string };

/**
 * One figure after a pane's title, styled like the readout above the chart. `reserve` is its widest value,
 * so the figures after it stay put while the crosshair moves.
 */
export type HeadingItem = { swatch?: string | undefined; label: string; value: string; reserve?: string };

const STRIP_PADDING = 8;
const ITEM_GAP = 10;
const SWATCH = 10;
const SWATCH_GAP = 4;

/**
 * The strip takes `share` of the pane's height, the same share its price scale must leave empty with
 * `scaleMargins.top`, so the two stay matched at any size. It covers the grid lines behind the text.
 * `setItems` adds figures after the title, on a second line when the pane is too narrow for one.
 */
export class PaneHeading implements ISeriesPrimitive<Time> {
  private host: Attached | null = null;
  private items: readonly HeadingItem[] = [];
  private itemsKey = "";
  private readonly views: readonly IPrimitivePaneView[];

  constructor(
    private readonly text: string,
    private readonly share: number,
    private readonly style: HeadingStyle,
  ) {
    const renderer: IPrimitivePaneRenderer = { draw: (target) => this.paint(target) };
    this.views = [{ zOrder: () => "top", renderer: () => renderer }];
  }

  attached(host: Attached): void {
    this.host = host;
  }

  detached(): void {
    this.host = null;
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }

  /** Called on every crosshair move, so it repaints only when a figure changed. */
  setItems(items: readonly HeadingItem[]): void {
    const key = JSON.stringify(items);
    if (key === this.itemsKey) return;
    this.itemsKey = key;
    this.items = items;
    this.host?.requestUpdate();
  }

  private width(context: CanvasRenderingContext2D, text: string, weight = ""): number {
    context.font = `${weight} ${this.style.font}`;
    return context.measureText(text).width;
  }

  /** Each item's left edge, line by line. The title starts the first line. */
  private layout(context: CanvasRenderingContext2D, available: number) {
    const lines: { item: HeadingItem; x: number }[][] = [[]];
    let x = STRIP_PADDING + this.width(context, this.text) + ITEM_GAP;
    for (const item of this.items) {
      const swatch = item.swatch ? SWATCH + SWATCH_GAP : 0;
      const value = Math.max(this.width(context, item.value, "600"), this.width(context, item.reserve ?? "", "600"));
      const size = swatch + this.width(context, item.label) + SWATCH_GAP + value;
      if (x + size > available && x > STRIP_PADDING) {
        lines.push([]);
        x = STRIP_PADDING;
      }
      lines.at(-1)?.push({ item, x });
      x += size + ITEM_GAP;
    }
    return lines;
  }

  private paint(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context, mediaSize }) => {
      const height = Math.round(mediaSize.height * this.share);
      context.fillStyle = this.style.background;
      context.fillRect(0, 0, mediaSize.width, height);
      context.textBaseline = "middle";
      const lines = this.layout(context, mediaSize.width);
      const middle = (line: number) => (height * (line + 0.5)) / lines.length;

      context.font = this.style.font;
      context.fillStyle = this.style.color;
      context.fillText(this.text, STRIP_PADDING, middle(0));
      lines.forEach((line, index) => {
        const y = middle(index);
        for (const { item, x: left } of line) {
          let x = left;
          if (item.swatch) {
            context.fillStyle = item.swatch;
            context.beginPath();
            context.roundRect(x, y - SWATCH / 2, SWATCH, SWATCH, 2);
            context.fill();
            x += SWATCH + SWATCH_GAP;
          }
          context.fillStyle = this.style.noteColor;
          context.font = this.style.font;
          context.fillText(item.label, x, y);
          x += this.width(context, item.label) + SWATCH_GAP;
          context.font = `600 ${this.style.font}`;
          context.fillText(item.value, x, y);
        }
      });
    });
  }
}

export type TimeSpan = { from: UTCTimestamp; to: UTCTimestamp; fill: string };
/** `label` is a tag at the top of the line, in the line's colour, with `labelColor` text. */
export type TimeLine = { time: UTCTimestamp; color: string; width?: number; label?: string; labelColor?: string };

const TAG_HEIGHT = 20;
const TAG_PADDING = 6;

/**
 * `overHeading` is for a pane with a PaneHeading: attached after the heading, the marks paint over its
 * strip and the data. Otherwise they sit under the data. `clearTop` is the share of the pane at the top
 * that lines stay out of, so a dark line never runs through a heading's figures.
 */
export class TimeMarks implements ISeriesPrimitive<Time> {
  private host: Attached | null = null;
  private spans: TimeSpan[] = [];
  private lines: TimeLine[] = [];
  private readonly views: readonly IPrimitivePaneView[];

  constructor(
    private readonly labelFont = "",
    overHeading = false,
    private readonly clearTop = 0,
  ) {
    const renderer: IPrimitivePaneRenderer = { draw: (target) => this.paint(target) };
    const tags: IPrimitivePaneRenderer = { draw: (target) => this.paintTags(target) };
    this.views = [
      overHeading ? { zOrder: () => "top", renderer: () => renderer } : paneView((target) => this.paint(target)),
      // Over everything: under the data, the chart's grid lines would run through the tag's text.
      { zOrder: () => "top", renderer: () => tags },
    ];
  }

  attached(host: Attached): void {
    this.host = host;
  }

  detached(): void {
    this.host = null;
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }

  set(spans: TimeSpan[], lines: TimeLine[]): void {
    this.spans = spans;
    this.lines = lines;
    this.host?.requestUpdate();
  }

  private paint(target: CanvasRenderingTarget2D): void {
    const host = this.host;
    if (!host) return;
    const scale = host.chart.timeScale();
    target.useMediaCoordinateSpace(({ context, mediaSize }) => {
      for (const span of this.spans) {
        const from = scale.timeToCoordinate(span.from);
        const to = scale.timeToCoordinate(span.to);
        if (from === null || to === null) continue;
        context.fillStyle = span.fill;
        context.fillRect(from, 0, to - from, mediaSize.height);
      }
      for (const line of this.lines) {
        const x = scale.timeToCoordinate(line.time);
        if (x === null) continue;
        const left = Math.round(x);
        const top = Math.round(mediaSize.height * this.clearTop);
        context.fillStyle = line.color;
        context.fillRect(left, top, line.width ?? 1, mediaSize.height - top);
      }
    });
  }

  private paintTags(target: CanvasRenderingTarget2D): void {
    const host = this.host;
    if (!host) return;
    const scale = host.chart.timeScale();
    target.useMediaCoordinateSpace(({ context, mediaSize }) => {
      for (const line of this.lines) {
        const x = scale.timeToCoordinate(line.time);
        if (x === null || !line.label) continue;
        context.font = this.labelFont;
        const width = context.measureText(line.label).width + TAG_PADDING * 2;
        // Kept inside the pane when the forecast sits at its right edge, as in the longest history spans.
        const tag = Math.min(Math.round(x), mediaSize.width - width);
        context.fillStyle = line.color;
        context.beginPath();
        context.roundRect(tag, 0, width, TAG_HEIGHT, [0, 0, 4, 4]);
        context.fill();
        context.fillStyle = line.labelColor ?? line.color;
        context.textBaseline = "middle";
        context.fillText(line.label, tag + TAG_PADDING, TAG_HEIGHT / 2);
      }
    });
  }
}
