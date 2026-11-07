/**
 * The price history table: per period, the highest and lowest spot and imbalance prices. Only quarter-hours
 * before the viewing time count; the input is already limited to rows usable then.
 */
import type { ActualPoint } from "@/lib/api/client";

const HOUR_MS = 3_600_000;

export const PERIODS = [
  { key: "1d", label: "1 day", hours: 24 },
  { key: "1w", label: "1 week", hours: 7 * 24 },
  { key: "1m", label: "1 month", hours: 30 * 24 },
  { key: "3m", label: "3 months", hours: 90 * 24 },
  { key: "all", label: "All data", hours: null },
] as const;

export type Extreme = { price: number; at: string };

export type PeriodStats = {
  key: (typeof PERIODS)[number]["key"];
  label: string;
  spotHigh: Extreme | null;
  spotLow: Extreme | null;
  imbalanceHigh: Extreme | null;
  imbalanceLow: Extreme | null;
};

const time = (point: ActualPoint) => new Date(point.delivery_start_utc).getTime();

function extreme(points: readonly ActualPoint[], read: (point: ActualPoint) => number | null, sign: 1 | -1): Extreme | null {
  let best: Extreme | null = null;
  for (const point of points) {
    const value = read(point);
    if (value !== null && (best === null || sign * value > sign * best.price)) best = { price: value, at: point.delivery_start_utc };
  }
  return best;
}

export function priceHistory(points: readonly ActualPoint[], origin: string): PeriodStats[] {
  const end = new Date(origin).getTime();
  const past = points.filter((point) => time(point) < end);
  const first = past.reduce((earliest, point) => Math.min(earliest, time(point)), end);

  return PERIODS.map((period) => {
    const start = period.hours === null ? first : end - period.hours * HOUR_MS;
    const inPeriod = past.filter((point) => time(point) >= start);
    return {
      key: period.key,
      label: period.label,
      spotHigh: extreme(inPeriod, (point) => point.spot, 1),
      spotLow: extreme(inPeriod, (point) => point.spot, -1),
      imbalanceHigh: extreme(inPeriod, (point) => point.imbalance_price, 1),
      imbalanceLow: extreme(inPeriod, (point) => point.imbalance_price, -1),
    };
  });
}
