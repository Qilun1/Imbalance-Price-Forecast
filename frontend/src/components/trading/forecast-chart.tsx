"use client";

import { useEffect, useMemo, useRef } from "react";

import type { ActualPoint, Forecast } from "@/lib/api/client";
import { buildRows, type ChartRow, type ChartWindow, ForecastView, rowTime } from "@/lib/chart/forecast-view";
import {
  formatDateTime,
  formatPercent,
  formatPrice,
  formatPriceRange,
  formatShortDateTime,
  formatWindow,
  NO_VALUE,
  PRICE_UNIT,
} from "@/lib/format";
import { directionLabel, directionOf } from "@/lib/forecast";

import { Readout, ReadoutRow, type ReadoutSpec } from "./chart-readout";

type Field = ReadoutSpec & { read: (row: ChartRow) => string };

const PRICE_FIELDS: readonly Field[] = [
  { key: "actual", label: "Actual", swatch: "bg-ink", width: "min-w-12", read: (row) => formatPrice(row.actual ?? row.outcome) },
  { key: "spot", label: "Spot", swatch: "bg-chart-spot", width: "min-w-12", read: (row) => formatPrice(row.spot) },
  { key: "p50", label: "Forecast", swatch: "bg-series-1", width: "min-w-12", read: (row) => formatPrice(row.p50) },
  {
    key: "range",
    label: "Prediction interval",
    swatch: "bg-chart-band",
    width: "min-w-28",
    read: (row) => (row.p10 === null || row.p90 === null ? NO_VALUE : formatPriceRange(row.p10, row.p90)),
  },
];

const DIRECTION_FIELDS: readonly Field[] = [
  { key: "up", label: "Up", swatch: "bg-up", width: "min-w-9", read: (row) => formatPercent(row.pUp) },
  { key: "down", label: "Down", swatch: "bg-down", width: "min-w-9", read: (row) => formatPercent(row.pDown) },
  { key: "happened", label: "Happened", width: "min-w-10", read: (row) => (row.realised ? directionLabel(row.realised) : NO_VALUE) },
];

/** Written straight to the DOM: the crosshair moves too often to re-render React for it. */
function writeReadout(root: HTMLElement | null, row: ChartRow | null): void {
  if (!root || !row) return;
  const time = rowTime(row);
  const at = root.querySelector("[data-field=time]");
  if (at) at.textContent = formatShortDateTime(time);
  for (const field of [...PRICE_FIELDS, ...DIRECTION_FIELDS]) {
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
    "Use the left and right arrow keys to read each quarter-hour. The Next 10 h table holds the same values."
  );
}

export default function ForecastChart({
  forecast,
  history,
  outcome,
  windows,
  spanHours,
}: {
  forecast: Forecast;
  history: readonly ActualPoint[];
  outcome: readonly ActualPoint[];
  windows: readonly ChartWindow[];
  /** Hours of history in view when the chart opens; null for all of it. */
  spanHours: number | null;
}) {
  const host = useRef<HTMLDivElement>(null);
  const readout = useRef<HTMLDivElement>(null);
  const view = useRef<ForecastView | null>(null);
  const resting = useRef<ChartRow | null>(null);

  const rows = useMemo(() => buildRows(forecast, history, outcome), [forecast, history, outcome]);
  const showsOutcome = outcome.length > 0;

  useEffect(() => {
    if (!host.current) return;
    const chart = new ForecastView(host.current, (row) => writeReadout(readout.current, row ?? resting.current));
    view.current = chart;
    return () => {
      chart.dispose();
      view.current = null;
    };
  }, []);

  useEffect(() => {
    resting.current = rows.find((row) => row.p50 !== null) ?? null;
    view.current?.update({ rows, origin: forecast.origin_utc, windows, spanHours });
    writeReadout(readout.current, resting.current);
  }, [rows, forecast.origin_utc, windows, spanHours]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <Readout ref={readout}>
        <ReadoutRow fields={PRICE_FIELDS} showsTime />
        <ReadoutRow fields={DIRECTION_FIELDS}>
          {/* Here rather than in the panel header, so turning the switch on never moves the header row. */}
          {showsOutcome ? (
            <span
              className="ml-auto min-w-0 truncate text-xs text-stone"
              title="The black line after “Forecast” is what really happened. It was not known when the forecast was made."
            >
              Black line: what happened
            </span>
          ) : null}
        </ReadoutRow>
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
