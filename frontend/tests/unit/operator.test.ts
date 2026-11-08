import { describe, expect, it } from "vitest";

import type { Alert, ForecastStep, FuelSnapshot, UmmMessage } from "@/lib/api/client";
import { formatQuarterHours } from "@/lib/format";
import { costLight, fuelRows, heatCosts, heatPlan, na4Messages, plantSide } from "@/lib/operator";

function step(index: number, fields: Partial<ForecastStep> = {}): ForecastStep {
  return {
    step: index + 1,
    delivery_start_utc: new Date(Date.UTC(2026, 9, 23, 12, index * 15)).toISOString().replace(".000Z", "Z"),
    p10: 20,
    p50: 40,
    p90: 80,
    p_up: 0.2,
    p_down: 0.79,
    p_none: 0.01,
    p_spike_high: 0.05,
    p_spike_low: 0.03,
    spot: 30,
    drivers: [],
    ...fields,
  };
}

function alert(fields: Partial<Alert>): Alert {
  return {
    kind: "spike_risk",
    severity: "watch",
    title: "Risk of an exceptionally high price",
    message: "",
    check: "",
    window_start_utc: "2026-10-23T12:00:00Z",
    window_end_utc: "2026-10-23T13:00:00Z",
    drivers: [],
    evidence: {},
    ...fields,
  };
}

function message(fields: Partial<UmmMessage>): UmmMessage {
  return {
    message_id: "m1",
    version: 1,
    kind: "generation",
    unplanned: true,
    units: ["Na4CHP"],
    fuel: "biomass",
    unavailable_mw: 145,
    event_start_utc: "2026-10-23T11:20:00Z",
    event_stop_utc: "2026-10-23T17:55:00Z",
    publication_utc: "2026-10-23T11:30:00Z",
    fresh: true,
    reason: null,
    url: "https://umm.nordpoolgroup.com/#/messages/m1/1",
    ...fields,
  };
}

const steps = Array.from({ length: 8 }, (_, index) => step(index));

const snapshot = {
  heat: { heat_only_boiler_eur_mwh: 43, e_boiler_cheaper_below_spot: 36.8 },
  chp: {
    unit: "NA4",
    by_fuel: [
      { fuel: "milled_peat", fuel_eur_mwh_incl_co2: 46, power_cost_after_heat_credit: 45 },
      { fuel: "srf", fuel_eur_mwh_incl_co2: null, power_cost_after_heat_credit: null },
      { fuel: "forest_chips", fuel_eur_mwh_incl_co2: 38, power_cost_after_heat_credit: 10 },
    ],
  },
  assumptions: { EB: { eta: 0.5, adders_eur_mwh: 5 } },
} as FuelSnapshot;

describe("plantSide", () => {
  it("puts a high-price risk on fuel and a low-price risk on heat, by the forecast's own numbers", () => {
    const lowSteps = steps.map((s) => ({ ...s, p_spike_high: 0.01, p_spike_low: 0.6 }));
    expect(plantSide(alert({}), steps)).toBe("fuel");
    expect(plantSide(alert({}), lowSteps)).toBe("heat");
  });

  it("follows the more likely regulation direction", () => {
    expect(plantSide(alert({ kind: "regulation_expected", title: "Down-regulation expected" }), steps)).toBe("heat");
  });

  it("decides an expert review by its spike side", () => {
    expect(plantSide(alert({ kind: "expert_review", severity: "review" }), steps)).toBe("fuel");
  });

  it("leaves market-wide situations to neither", () => {
    expect(plantSide(alert({ kind: "conflicting_signals" }), steps)).toBeNull();
  });
});

describe("na4Messages", () => {
  it("keeps NA4's messages only", () => {
    expect(na4Messages([message({}), message({ units: ["Olkiluoto 3"] })])).toHaveLength(1);
  });
});

describe("heatPlan", () => {
  it("picks the electric boiler below the break-even spot, and knows nothing without spot", () => {
    const mixed = [step(0, { spot: 10 }), step(1, { spot: 50 }), step(2, { spot: null })];
    expect(heatPlan(mixed, 30)).toEqual(["electric", "fuel", null]);
    expect(heatPlan(mixed, null)).toEqual([null, null, null]);
  });
});

describe("fuelRows", () => {
  it("orders by power cost, unpriced fuels last, and counts the quarter-hours the forecast covers", () => {
    const prices = [step(0, { p50: 50 }), step(1, { p50: 20 }), step(2, { p50: 5 })];
    expect(fuelRows(snapshot, prices).map((row) => [row.fuel, row.coveredQuarters])).toEqual([
      ["forest_chips", 2],
      ["milled_peat", 1],
      ["srf", 0],
    ]);
  });
});

describe("heatCosts", () => {
  it("puts both boilers in euros per MWh of heat, skipping quarter-hours without spot", () => {
    const mixed = [step(0, { spot: 10 }), step(1, { spot: 50 }), step(2, { spot: null })];
    expect(heatCosts(mixed, snapshot)).toEqual([
      { time: mixed[0]!.delivery_start_utc, electric: 30, chips: 43 },
      { time: mixed[1]!.delivery_start_utc, electric: 110, chips: 43 },
    ]);
  });

  it("agrees with the break-even spot on which boiler is cheaper", () => {
    const breakEven = 43 * 0.5 - 5;
    const around = [step(0, { spot: breakEven - 1 }), step(1, { spot: breakEven + 1 })];
    expect(heatCosts(around, snapshot).map((point) => (point.electric < point.chips ? "electric" : "fuel"))).toEqual(
      heatPlan(around, breakEven),
    );
  });

  it("is empty without a chip boiler price", () => {
    expect(heatCosts(steps, { ...snapshot, heat: { ...snapshot.heat, heat_only_boiler_eur_mwh: null } })).toEqual([]);
  });
});

describe("costLight", () => {
  it("is green when the average forecast covers the cost, yellow when only the peak does, red otherwise", () => {
    const prices = [step(0, { p50: 20 }), step(1, { p50: 60 })];
    expect([30, 50, 70].map((cost) => costLight(cost, prices))).toEqual(["green", "yellow", "red"]);
    expect(costLight(30, [])).toBeNull();
  });
});

describe("formatQuarterHours", () => {
  it("writes quarter-hours as hours", () => {
    expect([0, 4, 14, 13].map(formatQuarterHours)).toEqual(["0 h", "1 h", "3.5 h", "3.25 h"]);
  });
});
