"use client";

import { useEffect, useRef } from "react";

import type { HindsightPoint } from "@/lib/api/client";
import { HindsightView } from "@/lib/chart/hindsight-view";
import { formatDayRange } from "@/lib/format";

const LEGEND = [
  { label: "Actual", swatch: "bg-ink" },
  { label: "Forecast P50", swatch: "bg-series-1" },
  { label: "P10–P90", swatch: "bg-chart-band" },
  { label: "Baseline", swatch: "bg-ash" },
];

export default function HindsightChart({ points, leadHours }: { points: readonly HindsightPoint[]; leadHours: number }) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<HindsightView | null>(null);

  useEffect(() => {
    if (!host.current) return;
    const chart = new HindsightView(host.current);
    view.current = chart;
    return () => {
      chart.dispose();
      view.current = null;
    };
  }, []);

  useEffect(() => {
    view.current?.update(points);
  }, [points]);

  const first = points[0]?.delivery_start_utc;
  const last = points.at(-1)?.delivery_start_utc;
  const span = first && last ? formatDayRange(first, last) : "this period";

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <ul className="flex shrink-0 flex-wrap gap-x-4 text-xs text-muted-foreground" aria-hidden>
        {LEGEND.map(({ label, swatch }) => (
          <li key={label} className="inline-flex items-center gap-1.5">
            <span className={`size-2 rounded-xs ${swatch}`} />
            {label}
          </li>
        ))}
      </ul>
      <div
        ref={host}
        role="img"
        aria-label={`Forecast made ${leadHours} hours ahead against the actual price, ${span}. The scores beside this chart summarise it.`}
        className="min-h-0 flex-1"
      />
    </div>
  );
}
