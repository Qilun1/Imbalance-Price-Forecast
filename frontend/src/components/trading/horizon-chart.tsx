"use client";

import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import { type ChartConfig, ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import type { ScoreSet } from "@/lib/api/client";
import { formatPrice, formatScore } from "@/lib/format";

const config = {
  model: { label: "Model", color: "var(--color-series-1)" },
  baseline: { label: "Baseline", color: "var(--color-ash)" },
} satisfies ChartConfig;

const BAR_RADIUS: [number, number, number, number] = [4, 4, 0, 0];

/** How far ahead to trust the forecast: average error by how many hours ahead it was made. */
export function HorizonChart({ model, baseline }: { model: ScoreSet; baseline: ScoreSet | null | undefined }) {
  const baselineByHour = new Map(baseline?.by_horizon.map((row) => [row.horizon_hour, row.mae_p50]));
  const rows = model.by_horizon.map((row) => ({
    hour: row.horizon_hour,
    model: row.mae_p50,
    baseline: baselineByHour.get(row.horizon_hour) ?? null,
  }));
  return (
    <ChartContainer config={config} className="aspect-auto h-full min-h-48 w-full">
      <BarChart data={rows} barGap={2} accessibilityLayer>
        <CartesianGrid vertical={false} stroke="var(--color-chart-grid)" />
        <XAxis dataKey="hour" tickLine={false} axisLine={false} tickMargin={6} />
        <YAxis tickLine={false} axisLine={false} width={40} tickFormatter={(value: number) => formatScore(value, 0)} />
        <ChartTooltip
          content={
            <ChartTooltipContent
              labelFormatter={(hour) => `${hour} ${hour === 1 ? "hour" : "hours"} ahead`}
              formatter={(value, name) => (
                <span className="flex w-full justify-between gap-3">
                  <span className="text-muted-foreground">{name === "model" ? "Model" : "Baseline"}</span>
                  <span>{typeof value === "number" ? formatPrice(value) : ""}</span>
                </span>
              )}
            />
          }
        />
        <ChartLegend content={<ChartLegendContent />} />
        <Bar dataKey="model" fill="var(--color-model)" radius={BAR_RADIUS} />
        <Bar dataKey="baseline" fill="var(--color-baseline)" radius={BAR_RADIUS} />
      </BarChart>
    </ChartContainer>
  );
}
