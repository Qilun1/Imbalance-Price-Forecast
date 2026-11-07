import { describe, expect, it } from "vitest";

import type { Changes, Forecast, ForecastStep, HindsightPoint } from "@/lib/api/client";
import { exposure } from "@/lib/exposure";
import { directionOf, evidenceItems, headline, rankDrivers, revisionTrail, spread, stepsInWindow, upToLastActual } from "@/lib/forecast";

const WIND = { id: "wind_fc", label: "Wind power forecast" };
const LOAD = { id: "cons_fc", label: "Consumption forecast" };

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

function forecast(steps: ForecastStep[], origin = "2026-10-23T12:00:00Z"): Forecast {
  return {
    as_of_utc: origin,
    origin_utc: origin,
    model: "test",
    data_cutoff_utc: null,
    data_age_minutes: null,
    spot_known_until_utc: null,
    steps,
  };
}

const NO_CHANGES: Changes = { as_of_utc: "", origin_utc: "", previous_origin_utc: null, largest_p50_change: null, points: [] };

describe("direction", () => {
  it("picks the most likely direction", () => {
    expect(directionOf(step(0))).toBe("down");
    expect(directionOf(step(0, { p_up: 0.7, p_down: 0.29 }))).toBe("up");
    expect(directionOf(step(0, { p_up: 0.1, p_down: 0.1, p_none: 0.8 }))).toBe("none");
  });
});

describe("spread against spot", () => {
  it("is missing when spot is not known", () => {
    expect(spread(step(0))).toBe(10);
    expect(spread(step(0, { spot: null }))).toBeNull();
  });
});

describe("windows", () => {
  it("includes the start and leaves out the end", () => {
    const steps = [step(0), step(1), step(2)];
    const window = { start: "2026-10-23T12:15:00Z", end: "2026-10-23T12:30:00Z" };
    expect(stepsInWindow(steps, window).map((s) => s.step)).toEqual([2]);
    expect(stepsInWindow(steps, null)).toHaveLength(3);
  });
});

describe("upToLastActual", () => {
  const points = (...actuals: (number | null)[]): HindsightPoint[] =>
    actuals.map((actual, index) => ({
      delivery_start_utc: step(index).delivery_start_utc,
      p10: 20,
      p50: 40,
      p90: 80,
      baseline_p50: null,
      actual,
      spot: 30,
    }));

  it("ends the chart at the last price that is known", () => {
    const shown = upToLastActual(points(50, 60, null, null));
    expect(shown.map((point) => point.actual)).toEqual([50, 60]);
  });

  it("keeps a gap earlier in the period as a gap", () => {
    const shown = upToLastActual(points(50, null, 70, null));
    expect(shown.map((point) => point.actual)).toEqual([50, null, 70]);
  });

  it("leaves a period with every price known as it is", () => {
    expect(upToLastActual(points(50, 60))).toHaveLength(2);
  });

  it("shows nothing when no price is known yet", () => {
    expect(upToLastActual(points(null, null))).toEqual([]);
  });
});

describe("headline", () => {
  it("averages the next hour and finds the highest and lowest price in the whole horizon", () => {
    const steps = [0, 1, 2, 3, 4, 5].map((i) => step(i, { p50: 40 + i * 10 }));
    steps[5] = step(5, { p50: 15 });
    steps[4] = step(4, { p50: 120 });
    const result = headline(forecast(steps), NO_CHANGES);
    expect(result?.nextHour.p50).toBe((40 + 50 + 60 + 70) / 4);
    expect(result?.highest).toEqual({ price: 120, at: steps[4]?.delivery_start_utc });
    expect(result?.lowest).toEqual({ price: 15, at: steps[5]?.delivery_start_utc });
    expect(result?.revision).toBeNull();
    expect(result?.nextHour.change).toBeNull();
  });

  it("reads the direction across the whole next hour, not its first quarter-hour", () => {
    const up = { p_up: 0.6, p_down: 0.3, p_none: 0.1 };
    const down = { p_up: 0.1, p_down: 0.8, p_none: 0.1 };
    const steps = [step(0, up), step(1, down), step(2, down), step(3, down), step(4, up), step(5, up), step(6, up), step(7, up)];
    const result = headline(forecast(steps), NO_CHANGES);
    expect(result?.direction.direction).toBe("down");
    expect(result?.direction.probability).toBeCloseTo((0.3 + 0.8 * 3) / 4);
  });

  it("takes the largest revision by size, keeping its sign", () => {
    const steps = [step(0), step(1), step(2), step(3), step(4)];
    const point = (at: string, change: number) => ({
      delivery_start_utc: at,
      p50: 0,
      p50_previous: 0,
      p50_change: change,
      p_up_change: 0,
      p_spike_high_change: 0,
      p_spike_low_change: 0,
    });
    const at = steps.map((s) => s.delivery_start_utc) as [string, string, string, string, string];
    const changes = { ...NO_CHANGES, previous_origin_utc: "2026-10-23T11:00:00Z", points: [point(at[1], 5), point(at[4], -30)] };
    const result = headline(forecast(steps), changes);
    expect(result?.revision).toEqual({ change: -30, at: at[4], since: "2026-10-23T11:00:00Z" });
    expect(result?.nextHour.change).toBe(5);
  });

  it("gives nothing for an empty forecast", () => {
    expect(headline(forecast([]), undefined)).toBeNull();
  });
});

describe("drivers", () => {
  it("ranks by how many quarter-hours name a driver", () => {
    const steps = [step(0, { drivers: [WIND, LOAD] }), step(1, { drivers: [LOAD] }), step(2, { drivers: [LOAD] })];
    expect(rankDrivers(steps)).toEqual([
      { ...LOAD, quarters: 3 },
      { ...WIND, quarters: 1 },
    ]);
  });

  it("respects the limit and handles no drivers", () => {
    expect(rankDrivers([step(0, { drivers: [WIND, LOAD] })], 1)).toHaveLength(1);
    expect(rankDrivers([step(0)])).toEqual([]);
  });
});

describe("revision trail", () => {
  const window = { start: "2026-10-23T12:00:00Z", end: "2026-10-23T12:30:00Z" };

  it("orders by forecast time and skips forecasts that miss the window", () => {
    const later = forecast([step(0, { p50: 60, p_spike_high: 0.3 }), step(1, { p50: 80 })], "2026-10-23T11:00:00Z");
    const earlier = forecast([step(0, { p50: 40 })], "2026-10-23T10:00:00Z");
    const missing = forecast([step(8)], "2026-10-23T09:00:00Z");
    const trail = revisionTrail([later, missing, earlier], window);
    expect(trail.map((p) => p.origin)).toEqual(["2026-10-23T10:00:00Z", "2026-10-23T11:00:00Z"]);
    expect(trail[1]).toMatchObject({ p50: 70, p_spike_high: 0.3, quarters: 2 });
  });
});

describe("evidence", () => {
  it("labels known fields and ignores unknown ones", () => {
    const items = evidenceItems({ peak_probability: 0.42, something_new: 1 });
    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({ label: "Peak probability", kind: "probability", value: 0.42 });
  });
});

describe("exposure", () => {
  const steps = [step(0, { p10: 20, p50: 40, p90: 80, spot: 30 }), step(1, { p10: 0, p50: 50, p90: 130, spot: 30 })];

  it("charges a short position when the price is above spot", () => {
    const result = exposure(steps, "short", 4);
    expect(result.megawattHours).toBe(2);
    expect(result.expected).toBe(1 * 10 + 1 * 20);
    expect(result.low).toBe(1 * -10 + 1 * -30);
    expect(result.high).toBe(1 * 50 + 1 * 100);
  });

  it("flips the sign for a long position and keeps low below high", () => {
    const result = exposure(steps, "long", 4);
    expect(result.expected).toBe(-30);
    expect(result.low).toBe(-150);
    expect(result.high).toBe(40);
  });

  it("leaves out quarter-hours without spot and says how many", () => {
    const result = exposure([...steps, step(2, { spot: null })], "short", 4);
    expect(result.quarters).toBe(2);
    expect(result.missingSpot).toBe(1);
  });

  it("returns zero for no quarter-hours", () => {
    expect(exposure([], "short", 4)).toMatchObject({ expected: 0, quarters: 0 });
  });
});
