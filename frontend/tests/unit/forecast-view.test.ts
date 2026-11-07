import { describe, expect, it } from "vitest";

import type { ActualPoint, Forecast, ForecastStep } from "@/lib/api/client";
import { type DirectionRow, happenedRuns, readDirection } from "@/lib/chart/direction-pane";
import { buildRows, type ChartRow } from "@/lib/chart/forecast-view";
import { tint, withAlpha } from "@/lib/chart/theme";
import type { Direction } from "@/lib/forecast";
import { toUnixSeconds } from "@/lib/format";

const ORIGIN = "2026-10-23T12:00:00Z";
const BEFORE = "2026-10-23T11:45:00Z";
const AFTER_HORIZON = "2026-10-23T12:15:00Z";

const point = (at: string, price: number, direction: ActualPoint["direction"]): ActualPoint => ({
  delivery_start_utc: at,
  imbalance_price: price,
  direction,
  spot: 30,
});

const step = { delivery_start_utc: ORIGIN, p10: 20, p50: 40, p90: 80, p_up: 0.6, p_down: 0.3, p_none: 0.1 } as ForecastStep;
const forecast = { origin_utc: ORIGIN, steps: [step] } as Forecast;

const rowAt = (rows: readonly ChartRow[], at: string) => rows.find((row) => row.time === toUnixSeconds(at));

describe("buildRows", () => {
  it("adds what happened after the forecast time without passing it off as known then", () => {
    const rows = buildRows(forecast, [point(BEFORE, 50, "up")], [point(ORIGIN, 90, "down")]);
    expect(rowAt(rows, BEFORE)).toMatchObject({ actual: 50, realised: "up", outcome: null });
    expect(rowAt(rows, ORIGIN)).toMatchObject({ actual: null, realised: "down", outcome: 90 });
  });

  it("shows no direction after the forecast time until the outcome is asked for", () => {
    const rows = buildRows(forecast, [point(BEFORE, 50, "up")], []);
    expect(rowAt(rows, ORIGIN)).toMatchObject({ realised: null, pUp: 0.6 });
  });

  it("drops an outcome outside the forecast", () => {
    const rows = buildRows(forecast, [], [point(AFTER_HORIZON, 90, "down")]);
    expect(rowAt(rows, AFTER_HORIZON)).toBeUndefined();
  });
});

describe("happenedRuns", () => {
  const START = toUnixSeconds(BEFORE);
  const QUARTER = 900;
  const rows = (...directions: (Direction | null)[]) =>
    directions.map((realised, index) => ({ time: START + index * QUARTER, realised })) as DirectionRow[];
  const at = (quarters: number) => START + quarters * QUARTER;

  it("joins back-to-back quarter-hours of one direction", () => {
    expect(happenedRuns(rows("up", "up", "down"))).toEqual([
      { from: at(0), to: at(2), direction: "up" },
      { from: at(2), to: at(3), direction: "down" },
    ]);
  });

  it("leaves unknown quarter-hours empty, so no bar crosses the ones not yet published", () => {
    expect(happenedRuns(rows("up", null, null, "up"))).toEqual([
      { from: at(0), to: at(1), direction: "up" },
      { from: at(3), to: at(4), direction: "up" },
    ]);
  });

  it("draws nothing for a quarter-hour with no dominating direction", () => {
    expect(happenedRuns(rows("down", "none", "down"))).toEqual([
      { from: at(0), to: at(1), direction: "down" },
      { from: at(2), to: at(3), direction: "down" },
    ]);
  });
});

describe("chart colours", () => {
  it("reads the short hex a minified stylesheet gives, as well as the full one", () => {
    expect(tint("#a8391f", 0.5, "#fff")).toBe(tint("#a8391f", 0.5, "#ffffff"));
    expect(tint("#a8391f", 0.5, "#fff")).toBe("rgb(212,156,143)");
    expect(withAlpha("#000", 0.1)).toBe("rgba(0,0,0,0.1)");
  });
});

describe("readDirection", () => {
  const row = (fields: Partial<DirectionRow>): DirectionRow => ({
    time: toUnixSeconds(BEFORE) as DirectionRow["time"],
    pUp: null,
    pDown: null,
    realised: null,
    ...fields,
  });

  it("names the chances, then the direction with its own time and the price it decided", () => {
    const shown = row({ pUp: 0.33, pDown: 0.67 });
    const known = row({ realised: "down" });
    expect(readDirection(shown, known, -6.1)).toEqual({
      up: "33%",
      down: "67%",
      happened: { direction: "down", text: "11:45 Down, decided at −€6.1" },
    });
  });

  it("gives the direction alone when its price is not known", () => {
    expect(readDirection(null, row({ realised: "up" }), null).happened?.text).toBe("11:45 Up");
  });

  it("leaves what happened out until a direction is known", () => {
    expect(readDirection(row({ pUp: 0.5, pDown: 0.5 }), null, null).happened).toBeNull();
  });
});
