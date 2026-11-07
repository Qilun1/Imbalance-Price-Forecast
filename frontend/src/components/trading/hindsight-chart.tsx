"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";

import type { ActualPoint, HindsightPoint } from "@/lib/api/client";
import { readDirection } from "@/lib/chart/direction-pane";
import { type HindsightRow, HindsightView } from "@/lib/chart/hindsight-view";
import { upToLastActual } from "@/lib/forecast";
import { formatDayRange, formatPrice, formatPriceRange, formatShortDateTime, fromUnixSeconds, toUnixSeconds } from "@/lib/format";

import { DirectionText, Readout, ReadoutRow, type ReadoutSpec, writeDirectionText } from "./chart-readout";

type Field = ReadoutSpec & { read: (row: HindsightRow) => string };

/** The same names, colours and order as the Now chart's readout. */
const FIELDS: readonly Field[] = [
  { key: "actual", label: "Actual", swatch: "bg-ink", width: "min-w-[3em]", read: (row) => formatPrice(row.actual) },
  { key: "spot", label: "Spot", swatch: "bg-chart-spot", width: "min-w-[2.7em]", read: (row) => formatPrice(row.spot) },
  { key: "p50", label: "Forecast (Imbalance)", swatch: "bg-series-1", width: "min-w-[2.7em]", read: (row) => formatPrice(row.p50) },
  { key: "range", label: "Prediction interval", swatch: "bg-chart-band", width: "min-w-[8em]", read: (row) => formatPriceRange(row.p10, row.p90) },
];

/** Written straight to the DOM: the crosshair moves too often to re-render React for it. */
function writeReadout(root: HTMLElement | null, row: HindsightRow | null): void {
  if (!root) return;
  const time = row ? fromUnixSeconds(row.time) : null;
  const at = root.querySelector("[data-field=time]");
  if (at) at.textContent = time ? formatShortDateTime(time) : "";
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
  /** Observed prices over the same window; the spot line and the direction that happened come from here. */
  observed: readonly ActualPoint[];
  leadHours: number;
}) {
  const host = useRef<HTMLDivElement>(null);
  const readout = useRef<HTMLDivElement>(null);
  const view = useRef<HindsightView | null>(null);
  const latest = useRef<HindsightRow | null>(null);
  const lastDecided = useRef<HindsightRow | null>(null);

  const happened = useMemo(() => upToLastActual(points), [points]);

  const rows = useMemo(() => {
    const seen = new Map(observed.map((point) => [point.delivery_start_utc, point]));
    return happened.map((point) => {
      const known = seen.get(point.delivery_start_utc);
      return {
        time: toUnixSeconds(point.delivery_start_utc) as HindsightRow["time"],
        actual: point.actual,
        spot: known?.spot ?? null,
        p10: point.p10,
        p50: point.p50,
        p90: point.p90,
        // Null, not missing, while an API started before these fields existed is still running.
        pUp: point.p_up ?? null,
        pDown: point.p_down ?? null,
        realised: known?.direction ?? null,
      };
    });
  }, [happened, observed]);

  /** Without a row under the crosshair, the latest quarter-hour with a price. */
  const show = useCallback((row: HindsightRow | null) => {
    const shown = row ?? latest.current;
    writeReadout(readout.current, shown);
    const known = shown?.realised ? shown : lastDecided.current;
    const direction = readDirection(shown, known, known?.actual ?? null);
    view.current?.showDirection(direction);
    writeDirectionText(readout.current, direction);
  }, []);

  useEffect(() => {
    if (!host.current) return;
    const chart = new HindsightView(host.current, show);
    view.current = chart;
    return () => {
      chart.dispose();
      view.current = null;
    };
  }, [show]);

  useEffect(() => {
    latest.current = rows.findLast((row) => row.actual !== null) ?? rows.at(-1) ?? null;
    lastDecided.current = rows.findLast((row) => row.realised !== null) ?? null;
    view.current?.update(rows);
    show(null);
  }, [rows, show]);

  const first = happened[0]?.delivery_start_utc;
  const last = happened.at(-1)?.delivery_start_utc;
  const span = first && last ? formatDayRange(first, last) : "this period";

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <Readout ref={readout}>
        <ReadoutRow fields={FIELDS} showsTime />
        <DirectionText />
      </Readout>
      <div
        ref={host}
        role="img"
        aria-label={`Forecast made ${leadHours} hours ahead against the actual price and the Nord Pool spot price (violet), ${span}. In the lower pane solid bars show the direction that happened and pale fills the forecast's chances. The scores above summarise it.`}
        className="min-h-0 flex-1"
      />
    </div>
  );
}
