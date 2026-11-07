import { describe, expect, it } from "vitest";

import type { ActualPoint } from "@/lib/api/client";
import { priceHistory } from "@/lib/price-history";

const ORIGIN = "2026-10-23T09:00:00Z";
const HOUR = 3_600_000;

function at(hoursBefore: number, spot: number | null, imbalance: number | null = null): ActualPoint {
  return {
    delivery_start_utc: new Date(new Date(ORIGIN).getTime() - hoursBefore * HOUR).toISOString().replace(".000Z", "Z"),
    spot,
    imbalance_price: imbalance,
    direction: null,
  };
}

describe("priceHistory", () => {
  // Hourly points over 10 days: spot 50 except the last day at 60, one imbalance spike 3 days back.
  const points: ActualPoint[] = [];
  for (let hours = 240; hours >= 1; hours -= 1) points.push(at(hours, hours <= 24 ? 60 : 50, hours === 72 ? 400 : 20));
  points.push(at(-5, 999)); // day-ahead spot after the viewing time: not history

  const rows = priceHistory(points, ORIGIN);
  const row = (key: string) => rows.find((item) => item.key === key);

  it("finds highs and lows within each period only, ignoring prices after the viewing time", () => {
    expect(row("1d")?.imbalanceHigh?.price).toBe(20);
    expect(row("1w")?.imbalanceHigh).toEqual({ price: 400, at: points[240 - 72]?.delivery_start_utc });
    expect(row("all")?.spotHigh?.price).toBe(60);
    expect(row("all")?.spotLow?.price).toBe(50);
  });
});
