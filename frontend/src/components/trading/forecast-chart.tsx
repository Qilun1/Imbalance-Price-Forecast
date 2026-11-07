"use client";

import { useEffect, useMemo, useRef } from "react";

import type { ActualPoint, Forecast } from "@/lib/api/client";
import { buildRows, type ChartRow, type ChartWindow, ForecastView, rowTime } from "@/lib/chart/forecast-view";
import {
  formatClock,
  formatDate,
  formatDateTime,
  formatPercent,
  formatPrice,
  formatPriceRange,
  formatWindow,
  NO_VALUE,
  PRICE_UNIT,
} from "@/lib/format";

type Field = { key: string; label: string; swatch?: string; read: (row: ChartRow) => string };

const FIELDS: readonly Field[] = [
  { key: "actual", label: "Actual", swatch: "bg-ink", read: (row) => formatPrice(row.actual ?? row.outcome) },
  { key: "spot", label: "Spot", swatch: "bg-chart-spot", read: (row) => formatPrice(row.spot) },
  { key: "p50", label: "Forecast", swatch: "bg-series-1", read: (row) => formatPrice(row.p50) },
  {
    key: "range",
    label: "Likely range",
    swatch: "bg-chart-band",
    read: (row) => (row.p10 === null || row.p90 === null ? NO_VALUE : formatPriceRange(row.p10, row.p90)),
  },
];

/** Written straight to the DOM: the crosshair moves too often to re-render React for it. */
function writeReadout(root: HTMLElement | null, row: ChartRow | null): void {
  if (!root || !row) return;
  const time = rowTime(row);
  const at = root.querySelector("[data-field=time]");
  if (at) at.textContent = `${formatDate(time)} ${formatClock(time)}`;
  for (const field of FIELDS) {
    const target = root.querySelector(`[data-field=${field.key}]`);
    if (target) target.textContent = field.read(row);
  }
}

function describe(forecast: Forecast): string {
  const [first] = forecast.steps;
  const last = forecast.steps.at(-1);
  if (!first || !last) return "Forecast chart, no data.";
  const prices = forecast.steps.map((step) => step.p50);
  const highest = forecast.steps.reduce((top, step) => (step.p_spike_high > top.p_spike_high ? step : top));
  return (
    `Forecast chart for ${formatWindow(first.delivery_start_utc, last.delivery_start_utc)}, made ${formatDateTime(forecast.origin_utc)}. ` +
    `P50 runs from ${formatPrice(Math.min(...prices))} to ${formatPrice(Math.max(...prices))} ${PRICE_UNIT}. ` +
    `Highest risk of an exceptionally high price is ${formatPercent(highest.p_spike_high)} at ${formatDateTime(highest.delivery_start_utc)}. ` +
    "The Nord Pool spot price is the purple line. " +
    "Use the left and right arrow keys to read each quarter-hour. The Next 10 h table holds the same values."
  );
}

export default function ForecastChart({
  forecast,
  history,
  outcome,
  margin,
  windows,
  spanHours,
}: {
  forecast: Forecast;
  history: readonly ActualPoint[];
  outcome: readonly ActualPoint[];
  margin: number;
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
    view.current?.update({ rows, origin: forecast.origin_utc, margin, windows, spanHours });
    writeReadout(readout.current, resting.current);
  }, [rows, forecast.origin_utc, margin, windows, spanHours]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div ref={readout} className="flex h-5 shrink-0 items-baseline gap-x-5 overflow-hidden text-xs whitespace-nowrap">
        <span data-field="time" className="min-w-30 font-medium text-ink" />
        {FIELDS.map((field) => (
          <span key={field.key} className="inline-flex items-baseline gap-1.5">
            <span className={`size-2 self-center rounded-xs ${field.swatch}`} aria-hidden />
            <span className="text-muted-foreground">{field.label}</span>
            <span data-field={field.key} className="text-ink" />
          </span>
        ))}
        {/* Here rather than in the panel header, so turning the switch on never moves the header row. */}
        {showsOutcome ? (
          <span
            className="ml-auto min-w-0 truncate text-muted-foreground"
            title="The black line after “Forecast” is what really happened. It was not known when the forecast was made."
          >
            Black line: what happened
          </span>
        ) : null}
      </div>
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
