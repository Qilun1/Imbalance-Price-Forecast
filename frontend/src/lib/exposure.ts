/**
 * What an open position could cost compared with spot. The brief's glossary: the imbalance cost depends
 * on the volume, the direction and the price of the imbalance. The volume here is the expert's own
 * input, because open data cannot show the real position.
 *
 * A short position buys the missing energy at the imbalance price, so a price above spot is a cost.
 * A long position sells the surplus at the imbalance price, so a price below spot is a cost.
 */
import type { ForecastStep } from "@/lib/api/client";

import { STEPS_PER_HOUR } from "./forecast";

export type Side = "short" | "long";

export type Exposure = {
  /** Positive means extra cost compared with spot. */
  expected: number;
  /** Sum of each quarter-hour's P10 and P90. The real range is narrower: all of them rarely hit at once. */
  low: number;
  high: number;
  quarters: number;
  megawattHours: number;
  /** Quarter-hours left out because their spot price is not known yet. */
  missingSpot: number;
};

export function exposure(steps: readonly ForecastStep[], side: Side, megawatts: number): Exposure {
  const energy = megawatts / STEPS_PER_HOUR;
  const sign = side === "short" ? 1 : -1;
  const priced = steps.filter((step) => step.spot !== null);
  const total = (price: (step: ForecastStep) => number) =>
    priced.reduce((sum, step) => sum + sign * energy * (price(step) - (step.spot as number)), 0);
  const ends = [total((step) => step.p10), total((step) => step.p90)];
  return {
    expected: total((step) => step.p50),
    low: Math.min(...ends),
    high: Math.max(...ends),
    quarters: priced.length,
    megawattHours: energy * priced.length,
    missingSpot: steps.length - priced.length,
  };
}
