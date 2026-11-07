/**
 * Two small drawing additions Lightweight Charts has no series for.
 *
 * StepBand fills between two values that hold for a whole quarter-hour: the P10-P90 fan and the spot +/- 50
 * zone. TimeMarks shades time windows and draws a vertical line at the forecast time, in any pane.
 * PaneHeading gives a pane a title in its own strip, clear of the data.
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

export type HeadingStyle = { font: string; color: string; background: string };

/**
 * The strip takes `share` of the pane's height, the same share its price scale must leave empty with
 * `scaleMargins.top`, so the two stay matched at any size. It covers the grid lines behind the text.
 */
export class PaneHeading implements ISeriesPrimitive<Time> {
  private readonly views: readonly IPrimitivePaneView[];

  constructor(
    private readonly text: string,
    private readonly share: number,
    private readonly style: HeadingStyle,
  ) {
    const renderer: IPrimitivePaneRenderer = { draw: (target) => this.paint(target) };
    this.views = [{ zOrder: () => "top", renderer: () => renderer }];
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }

  private paint(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context, mediaSize }) => {
      const height = Math.round(mediaSize.height * this.share);
      context.fillStyle = this.style.background;
      context.fillRect(0, 0, mediaSize.width, height);
      context.font = this.style.font;
      context.fillStyle = this.style.color;
      context.textBaseline = "middle";
      context.fillText(this.text, 8, height / 2);
    });
  }
}

export type TimeSpan = { from: UTCTimestamp; to: UTCTimestamp; fill: string };
export type TimeLine = { time: UTCTimestamp; color: string; label?: string; labelColor?: string };

export class TimeMarks implements ISeriesPrimitive<Time> {
  private host: Attached | null = null;
  private spans: TimeSpan[] = [];
  private lines: TimeLine[] = [];
  private readonly views: readonly IPrimitivePaneView[];

  constructor(private readonly labelFont = "") {
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
        context.fillStyle = line.color;
        context.fillRect(Math.round(x), 0, 1, mediaSize.height);
        if (line.label) {
          context.font = this.labelFont;
          context.fillStyle = line.labelColor ?? line.color;
          context.fillText(line.label, Math.round(x) + 4, 12);
        }
      }
    });
  }
}
