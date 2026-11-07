"use client";

import { useEffect, useRef } from "react";

import { RevisionView } from "@/lib/chart/revision-view";
import { formatClock, formatPercent, formatPrice, PRICE_UNIT } from "@/lib/format";
import type { RevisionPoint } from "@/lib/forecast";

function describe(points: readonly RevisionPoint[]): string {
  const [first] = points;
  const last = points.at(-1);
  if (!first || !last) return "How the forecast for this window developed: no data.";
  return (
    `How the forecast for this window developed over ${points.length} updates. Average P50 went from ${formatPrice(first.p50)} at ` +
    `${formatClock(first.origin)} to ${formatPrice(last.p50)} ${PRICE_UNIT} at ${formatClock(last.origin)}. Peak high-price risk went from ` +
    `${formatPercent(first.p_spike_high)} to ${formatPercent(last.p_spike_high)}.`
  );
}

export default function RevisionChart({ points }: { points: readonly RevisionPoint[] }) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<RevisionView | null>(null);

  useEffect(() => {
    if (!host.current) return;
    const chart = new RevisionView(host.current);
    view.current = chart;
    return () => {
      chart.dispose();
      view.current = null;
    };
  }, []);

  useEffect(() => {
    view.current?.update(points);
  }, [points]);

  return <div ref={host} role="img" aria-label={describe(points)} className="h-56 w-full" />;
}
