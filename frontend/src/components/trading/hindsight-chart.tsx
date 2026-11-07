"use client";

import { useEffect, useMemo, useRef } from "react";

import type { ActualPoint, HindsightPoint } from "@/lib/api/client";
import { type HindsightRow, HindsightView } from "@/lib/chart/hindsight-view";
import { formatClock, formatDate, formatDayRange, formatPrice, formatPriceRange, fromUnixSeconds, toUnixSeconds } from "@/lib/format";

type Field = { key: string; label: string; swatch: string; read: (row: HindsightRow) => string };

/** The same names, colours and order as the Now chart's readout. */
const FIELDS: readonly Field[] = [
  { key: "actual", label: "Actual", swatch: "bg-ink", read: (row) => formatPrice(row.actual) },
  { key: "spot", label: "Spot", swatch: "bg-chart-spot", read: (row) => formatPrice(row.spot) },
  { key: "p50", label: "Forecast", swatch: "bg-series-1", read: (row) => formatPrice(row.p50) },
  { key: "range", label: "Likely range", swatch: "bg-chart-band", read: (row) => formatPriceRange(row.p10, row.p90) },
];

/** Written straight to the DOM: the crosshair moves too often to re-render React for it. */
function writeReadout(root: HTMLElement | null, row: HindsightRow | null): void {
  if (!root) return;
  const time = row ? fromUnixSeconds(row.time) : null;
  const at = root.querySelector("[data-field=time]");
  if (at) at.textContent = time ? `${formatDate(time)} ${formatClock(time)}` : "";
  for (const field of FIELDS) {
    const target = root.querySelector(`[data-field=${field.key}]`);
    if (target) target.textContent = row ? field.read(row) : "–";
  }
}

export default function HindsightChart({
  points,
  observed,
  leadHours,
}: {
  points: readonly HindsightPoint[];
  /** Observed prices over the same window; the spot line comes from here. */
  observed: readonly ActualPoint[];
  leadHours: number;
}) {
  const host = useRef<HTMLDivElement>(null);
  const readout = useRef<HTMLDivElement>(null);
  const view = useRef<HindsightView | null>(null);
  const latest = useRef<HindsightRow | null>(null);

  const rows = useMemo(() => {
    const spot = new Map(observed.map((point) => [point.delivery_start_utc, point.spot]));
    return points.map((point) => ({
      time: toUnixSeconds(point.delivery_start_utc) as HindsightRow["time"],
      actual: point.actual,
      spot: spot.get(point.delivery_start_utc) ?? null,
      p10: point.p10,
      p50: point.p50,
      p90: point.p90,
    }));
  }, [points, observed]);

  useEffect(() => {
    if (!host.current) return;
    const chart = new HindsightView(host.current, (row) => writeReadout(readout.current, row ?? latest.current));
    view.current = chart;
    return () => {
      chart.dispose();
      view.current = null;
    };
  }, []);

  useEffect(() => {
    latest.current = rows.findLast((row) => row.actual !== null) ?? rows.at(-1) ?? null;
    view.current?.update(rows);
    writeReadout(readout.current, latest.current);
  }, [rows]);

  const first = points[0]?.delivery_start_utc;
  const last = points.at(-1)?.delivery_start_utc;
  const span = first && last ? formatDayRange(first, last) : "this period";

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
      </div>
      <div
        ref={host}
        role="img"
        aria-label={`Forecast made ${leadHours} hours ahead against the actual price and the Nord Pool spot price (violet), ${span}. The scores above summarise it.`}
        className="min-h-0 flex-1"
      />
    </div>
  );
}
