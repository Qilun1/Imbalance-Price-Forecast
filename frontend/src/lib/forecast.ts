/** Reading a forecast: the plain calculations behind the KPI row, drivers and revision trail. */
import type { Alert, Changes, Driver, Forecast, ForecastStep } from "@/lib/api/client";

export const STEPS_PER_HOUR = 4;

export type Direction = "up" | "down" | "none";

export function directionOf(step: Pick<ForecastStep, "p_up" | "p_down" | "p_none">): Direction {
  if (step.p_up >= step.p_down && step.p_up >= step.p_none) return "up";
  return step.p_down >= step.p_none ? "down" : "none";
}

export function directionProbability(step: Pick<ForecastStep, "p_up" | "p_down" | "p_none">): number {
  return Math.max(step.p_up, step.p_down, step.p_none);
}

export function directionLabel(direction: Direction): string {
  return { up: "Up", down: "Down", none: "None" }[direction];
}

export function spread(step: Pick<ForecastStep, "p50" | "spot">): number | null {
  return step.spot === null ? null : step.p50 - step.spot;
}

export function isInWindow(deliveryStart: string, window: { start: string; end: string }): boolean {
  const time = new Date(deliveryStart).getTime();
  return time >= new Date(window.start).getTime() && time < new Date(window.end).getTime();
}

export function windowOf(alert: Alert): { start: string; end: string } {
  return { start: alert.window_start_utc, end: alert.window_end_utc };
}

export function stepsInWindow(steps: readonly ForecastStep[], window: { start: string; end: string } | null) {
  return window ? steps.filter((step) => isInWindow(step.delivery_start_utc, window)) : [...steps];
}

const mean = (values: readonly number[]) => values.reduce((sum, value) => sum + value, 0) / values.length;

/** The P50 at its highest (sign 1) or lowest (sign -1) quarter-hour; the first one on a tie. */
function extreme(steps: readonly ForecastStep[], sign: 1 | -1) {
  const top = steps.reduce((best, step) => (sign * step.p50 > sign * best.p50 ? step : best));
  return { price: top.p50, at: top.delivery_start_utc };
}

export type Headline = {
  nextHour: { p50: number; p10: number; p90: number; change: number | null };
  highest: { price: number; at: string };
  lowest: { price: number; at: string };
  direction: { direction: Direction; probability: number };
  revision: { change: number; at: string; since: string } | null;
};

/** The five numbers in the KPI row, or null when a forecast has no steps. */
export function headline(forecast: Forecast, changes: Changes | undefined): Headline | null {
  const { steps } = forecast;
  if (!steps.length) return null;
  const nextHour = steps.slice(0, STEPS_PER_HOUR);
  const likelihood = {
    p_up: mean(nextHour.map((step) => step.p_up)),
    p_down: mean(nextHour.map((step) => step.p_down)),
    p_none: mean(nextHour.map((step) => step.p_none)),
  };
  const points = changes?.points ?? [];
  const nextHourTimes = new Set(nextHour.map((step) => step.delivery_start_utc));
  const nextHourChanges = points.filter((point) => nextHourTimes.has(point.delivery_start_utc));
  const largest = points.reduce<(typeof points)[number] | null>(
    (best, point) => (best === null || Math.abs(point.p50_change) > Math.abs(best.p50_change) ? point : best),
    null,
  );
  return {
    nextHour: {
      p50: mean(nextHour.map((step) => step.p50)),
      p10: mean(nextHour.map((step) => step.p10)),
      p90: mean(nextHour.map((step) => step.p90)),
      change: nextHourChanges.length ? mean(nextHourChanges.map((point) => point.p50_change)) : null,
    },
    highest: extreme(steps, 1),
    lowest: extreme(steps, -1),
    direction: { direction: directionOf(likelihood), probability: directionProbability(likelihood) },
    revision:
      largest && changes?.previous_origin_utc
        ? { change: largest.p50_change, at: largest.delivery_start_utc, since: changes.previous_origin_utc }
        : null,
  };
}

export type RankedDriver = Driver & { quarters: number };

/** Drivers across some quarter-hours, ranked by how many quarter-hours name them. */
export function rankDrivers(steps: readonly ForecastStep[], limit = 6): RankedDriver[] {
  const counts = new Map<string, RankedDriver>();
  for (const step of steps) {
    for (const driver of step.drivers) {
      const known = counts.get(driver.id);
      if (known) known.quarters += 1;
      else counts.set(driver.id, { ...driver, quarters: 1 });
    }
  }
  return [...counts.values()].sort((a, b) => b.quarters - a.quarters || a.label.localeCompare(b.label)).slice(0, limit);
}

export type RevisionPoint = {
  origin: string;
  p50: number;
  p_spike_high: number;
  p_spike_low: number;
  quarters: number;
};

/** How one window looked in each earlier forecast that covered it. Forecasts missing it are left out. */
export function revisionTrail(forecasts: readonly Forecast[], window: { start: string; end: string }): RevisionPoint[] {
  const points: RevisionPoint[] = [];
  for (const forecast of forecasts) {
    const steps = stepsInWindow(forecast.steps, window);
    if (!steps.length) continue;
    points.push({
      origin: forecast.origin_utc,
      p50: mean(steps.map((step) => step.p50)),
      p_spike_high: Math.max(...steps.map((step) => step.p_spike_high)),
      p_spike_low: Math.max(...steps.map((step) => step.p_spike_low)),
      quarters: steps.length,
    });
  }
  return points.sort((a, b) => a.origin.localeCompare(b.origin));
}

/** A readable name for each `evidence` field an alert can carry. */
const EVIDENCE: Record<string, { label: string; kind: "probability" | "points" | "price" | "minutes" | "count" }> = {
  peak_probability: { label: "Peak probability", kind: "probability" },
  largest_rise: { label: "Largest rise", kind: "points" },
  largest_p50_change: { label: "Largest change", kind: "price" },
  largest_width: { label: "Widest P10–P90", kind: "price" },
  data_age_minutes: { label: "Data age", kind: "minutes" },
  signals: { label: "Overlapping signals", kind: "count" },
  direction_probability: { label: "Direction probability", kind: "probability" },
  peak_spike_probability: { label: "Peak risk", kind: "probability" },
};

export function evidenceItems(evidence: Alert["evidence"]) {
  return Object.entries(evidence).flatMap(([key, value]) => {
    const known = EVIDENCE[key];
    return known ? [{ key, value, ...known }] : [];
  });
}
