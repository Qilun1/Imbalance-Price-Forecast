"use client";

import { useEffect, useRef } from "react";

import { HeatView } from "@/lib/chart/heat-view";
import { formatPrice, formatQuarterHours } from "@/lib/format";
import type { HeatCostPoint } from "@/lib/operator";

function describe(points: readonly HeatCostPoint[]): string {
  const [first] = points;
  if (!first) return "Heat cost: no spot prices for these hours.";
  const electric = points.filter((point) => point.electric < point.chips).length;
  return (
    `Heat cost in euros per MWh of heat. The chip boiler costs ${formatPrice(first.chips)}. The electric boiler costs ` +
    `${formatPrice(first.electric)} now and is cheaper for ${formatQuarterHours(electric)} of the next ${formatQuarterHours(points.length)}.`
  );
}

export default function HeatChart({ points }: { points: readonly HeatCostPoint[] }) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<HeatView | null>(null);

  useEffect(() => {
    if (!host.current) return;
    const chart = new HeatView(host.current);
    view.current = chart;
    return () => {
      chart.dispose();
      view.current = null;
    };
  }, []);

  useEffect(() => {
    view.current?.update(points);
  }, [points]);

  return <div ref={host} role="img" aria-label={describe(points)} className="h-36 w-full" />;
}
