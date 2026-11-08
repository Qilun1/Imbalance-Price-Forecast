/**
 * The CHP screen: the Now screen with the plant's fuel figures beside it. These helpers decide what
 * those figures say and which of them a situation points at. They suggest where to look, never what to do.
 */
import type { Alert, ForecastStep, FuelSnapshot, UmmMessage } from "@/lib/api/client";
import { stepsInWindow, windowOf } from "@/lib/forecast";

/** Unit name of NA4 in Nord Pool's UMM. */
const NA4 = /na4/i;

export function na4Messages(messages: readonly UmmMessage[]): UmmMessage[] {
  return messages.filter((message) => message.units.some((unit) => NA4.test(unit)));
}

const mean = (values: number[]) => values.reduce((sum, value) => sum + value, 0) / Math.max(values.length, 1);

/**
 * Which part of the plant a situation is about, from the forecast's own probabilities in its window, not its
 * wording: high prices and up-regulation concern NA4's fuel and output, low prices and down-regulation the heat
 * source (electric boilers). Market-wide situations, such as disagreeing models, concern neither.
 */
export function plantSide(alert: Alert, steps: readonly ForecastStep[]): "heat" | "fuel" | null {
  const rows = stepsInWindow(steps, windowOf(alert));
  if (!rows.length) return null;
  // An expert review stacks a spike risk on expected regulation, so the spike side decides it too.
  if (alert.kind === "spike_risk" || alert.kind === "expert_review") {
    return mean(rows.map((step) => step.p_spike_high)) >= mean(rows.map((step) => step.p_spike_low)) ? "fuel" : "heat";
  }
  if (alert.kind === "regulation_expected") {
    return mean(rows.map((step) => step.p_up)) >= mean(rows.map((step) => step.p_down)) ? "fuel" : "heat";
  }
  return null;
}

export type HeatSource = "electric" | "fuel";

/** Per quarter-hour, the cheaper heat source: the electric boiler below the break-even spot, else the chip boiler. */
export function heatPlan(steps: readonly ForecastStep[], breakEven: number | null): (HeatSource | null)[] {
  return steps.map((step) => (step.spot === null || breakEven === null ? null : step.spot < breakEven ? "electric" : "fuel"));
}

export type FuelRow = { fuel: string; powerCost: number | null; fuelCost: number | null; coveredQuarters: number };

/** NA4's fuels, cheapest power first, each with the quarter-hours where the forecast price (P50) covers its cost. */
export function fuelRows(snapshot: FuelSnapshot, steps: readonly ForecastStep[]): FuelRow[] {
  return snapshot.chp.by_fuel
    .map(({ fuel, fuel_eur_mwh_incl_co2, power_cost_after_heat_credit }) => ({
      fuel,
      powerCost: power_cost_after_heat_credit,
      fuelCost: fuel_eur_mwh_incl_co2,
      coveredQuarters:
        power_cost_after_heat_credit === null ? 0 : steps.filter((step) => step.p50 >= power_cost_after_heat_credit).length,
    }))
    .sort((a, b) => (a.powerCost ?? Number.POSITIVE_INFINITY) - (b.powerCost ?? Number.POSITIVE_INFINITY));
}

export const FUEL_LABELS: Record<string, string> = {
  forest_chips: "Forest chips",
  milled_peat: "Milled peat",
  srf: "SRF",
  coal: "Coal (reserve)",
  natural_gas: "Natural gas",
  heavy_fuel_oil: "Heavy fuel oil",
};

export type HeatCostPoint = { time: string; electric: number; chips: number };

/**
 * € per MWh of heat at each quarter-hour, both on one scale: the electric boiler at that quarter-hour's spot
 * price, with grid fee and tax, against the chip boiler's cost. Where electric is lower, it is the cheaper heat.
 */
export function heatCosts(steps: readonly ForecastStep[], snapshot: FuelSnapshot): HeatCostPoint[] {
  const chips = snapshot.heat.heat_only_boiler_eur_mwh;
  const { eta, adders_eur_mwh: adders } = snapshot.assumptions.EB;
  if (chips === null) return [];
  return steps.flatMap((step) =>
    step.spot === null ? [] : [{ time: step.delivery_start_utc, electric: (step.spot + adders) / eta, chips }],
  );
}

/** Traffic light for a fuel's power cost: green, the average forecast covers it; yellow, only the peak; red, not even the peak. */
export function costLight(cost: number, steps: readonly ForecastStep[]): "green" | "yellow" | "red" | null {
  if (!steps.length) return null;
  const p50s = steps.map((step) => step.p50);
  if (cost <= mean(p50s)) return "green";
  return cost <= Math.max(...p50s) ? "yellow" : "red";
}
