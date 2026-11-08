"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";

import type { ActualPoint, Forecast } from "@/lib/api/client";
import { readDirection } from "@/lib/chart/direction-pane";
import { buildRows, type ChartRow, type ChartWindow, ForecastView, rowTime } from "@/lib/chart/forecast-view";
import {
  formatDateTime,
  formatPrice,
  formatPriceRange,
  formatShortDateTime,
  formatWindow,
  NO_VALUE,
  PRICE_UNIT,
  toUnixSeconds,
} from "@/lib/format";
import { directionOf } from "@/lib/forecast";

import { DirectionText, Readout, ReadoutRow, type ReadoutSpec, writeDirectionText } from "./chart-readout";

type Field = ReadoutSpec & { read: (row: ChartRow) => string };

const happenedPrice = (row: ChartRow) => row.actual ?? row.outcome;

const PRICE_FIELDS: readonly Field[] = [
  { key: "actual", label: "Actual", swatch: "bg-ink", width: "min-w-[3em]", read: (row) => formatPrice(happenedPrice(row)) },
  { key: "spot", label: "Spot", swatch: "bg-chart-spot", width: "min-w-[2.7em]", read: (row) => formatPrice(row.spot) },
  { key: "p50", label: "Forecast (Imbalance)", swatch: "bg-series-1", width: "min-w-[2.7em]", read: (row) => formatPrice(row.p50) },
  {
    key: "range",
    label: "Prediction interval",
    swatch: "bg-chart-band",
    width: "min-w-[8em]",
    read: (row) => (row.p10 === null || row.p90 === null ? NO_VALUE : formatPriceRange(row.p10, row.p90)),
  },
];

/** Written straight to the DOM: the crosshair moves too often to re-render React for it. */
function writeReadout(root: HTMLElement | null, row: ChartRow | null): void {
  if (!root || !row) return;
  const time = rowTime(row);
  const at = root.querySelector("[data-field=time]");
  if (at) at.textContent = formatShortDateTime(time);
  for (const field of PRICE_FIELDS) {
    const target = root.querySelector(`[data-field=${field.key}]`);
    if (target) target.textContent = field.read(row);
  }
}

function describe(forecast: Forecast): string {
  const { steps } = forecast;
  const [first] = steps;
  const last = steps.at(-1);
  if (!first || !last) return "Forecast chart, no data.";
  const prices = steps.map((step) => step.p50);
  const count = (direction: "up" | "down") => steps.filter((step) => directionOf(step) === direction).length;
  return (
    `Forecast chart for ${formatWindow(first.delivery_start_utc, last.delivery_start_utc)}, made ${formatDateTime(forecast.origin_utc)}. ` +
    `P50 runs from ${formatPrice(Math.min(...prices))} to ${formatPrice(Math.max(...prices))} ${PRICE_UNIT}. ` +
    `Balancing is most likely up in ${count("up")} and down in ${count("down")} of ${steps.length} quarter-hours. ` +
    "The Nord Pool spot price is the purple line. " +
    "In the lower pane solid bars show the direction that happened and pale fills the forecast's chances. " +
    "Use the left and right arrow keys to read each quarter-hour. The Next 10 h table holds the same values."
  );
}

export default function ForecastChart({
  forecast,
  history,
  outcome,
  windows,
  focus,
  spanHours,
}: {
  forecast: Forecast;
  history: readonly ActualPoint[];
  outcome: readonly ActualPoint[];
  windows: readonly ChartWindow[];
  /** A key figure's quarter-hours: shaded, with the readout on the first of them. */
  focus: { start: string; end: string } | null;
  /** Hours of history in view when the chart opens; null for all of it. */
  spanHours: number | null;
}) {
  const host = useRef<HTMLDivElement>(null);
  const readout = useRef<HTMLDivElement>(null);
  const view = useRef<ForecastView | null>(null);
  const resting = useRef<ChartRow | null>(null);
  const lastDecided = useRef<ChartRow | null>(null);

  const rows = useMemo(() => buildRows(forecast, history, outcome), [forecast, history, outcome]);

  /** Without a row under the crosshair, the picked key figure's quarter-hour or the first forecast one. */
  const show = useCallback((row: ChartRow | null) => {
    const shown = row ?? resting.current;
    writeReadout(readout.current, shown);
    const known = shown?.realised ? shown : lastDecided.current;
    const direction = readDirection(shown, known, known && happenedPrice(known));
    view.current?.showDirection(direction);
    writeDirectionText(readout.current, direction);
  }, []);

  useEffect(() => {
    if (!host.current) return;
    const chart = new ForecastView(host.current, show);
    view.current = chart;
    return () => {
      chart.dispose();
      view.current = null;
    };
  }, [show]);

  useEffect(() => {
    const focused = focus ? rows.find((row) => row.time === toUnixSeconds(focus.start)) : undefined;
    resting.current = focused ?? rows.find((row) => row.p50 !== null) ?? null;
    lastDecided.current = rows.findLast((row) => row.realised !== null) ?? null;
    view.current?.update({ rows, origin: forecast.origin_utc, windows, focus, spanHours });
    show(null);
  }, [rows, forecast.origin_utc, windows, focus, spanHours, show]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <Readout ref={readout}>
        <ReadoutRow fields={PRICE_FIELDS} showsTime />
        <DirectionText />
      </Readout>
      <div
        ref={host}
        role="img"
        aria-label={describe(forecast)}
        tabIndex={0}
        className="min-h-0 flex-1 rounded-md"
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
            event.preventDefault();
            view.current?.moveCursor(event.key === "ArrowLeft" ? -1 : 1);
          }
          if (event.key === "Escape") view.current?.clearCursor();
        }}
      />
    </div>
  );
}
