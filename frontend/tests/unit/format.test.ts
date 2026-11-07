import { describe, expect, it } from "vitest";

import {
  addHours,
  floorToHour,
  formatBetter,
  formatClock,
  formatClockUtc,
  formatDate,
  formatDateTime,
  formatDateTimeUtc,
  formatShortDateTime,
  formatMegawatts,
  formatMinutes,
  formatPercent,
  formatPoints,
  formatEuro,
  formatPrice,
  formatPriceAxis,
  formatPriceRange,
  formatPriceWithUnit,
  formatScore,
  formatSignedEuro,
  formatSignedPrice,
  formatWindow,
  formatWindowWithDay,
  fromUnixSeconds,
  fromUtcDate,
  hoursBetween,
  NO_VALUE,
  toApiTime,
  toCalendarDate,
  toUnixSeconds,
  utcHour,
} from "@/lib/format";

const MINUS = "−";

describe("prices", () => {
  it("uses one decimal, grouping and a true minus sign", () => {
    expect(formatPrice(63.85)).toBe("63.9");
    expect(formatPrice(-12.34)).toBe(`${MINUS}12.3`);
    expect(formatPrice(1234.5)).toBe("1,234.5");
    expect(formatPriceAxis(-49.6)).toBe(`${MINUS}50`);
    expect(formatPriceAxis(0.4)).toBe("0");
    expect(formatEuro(63.85)).toBe("€63.9");
    expect(formatEuro(-12.34)).toBe(`${MINUS}€12.3`);
    expect(formatEuro(67, { plus: true })).toBe("+€67.0");
    expect(formatEuro(97.9, { digits: 0 })).toBe("€98");
    expect(formatEuro(null)).toBe("–");
    expect(formatPrice(0)).toBe("0.0");
  });

  it("drops the sign when a value rounds to zero", () => {
    expect(formatPrice(-0.04)).toBe("0.0");
    expect(formatSignedPrice(-0.04)).toBe("0.0");
    expect(formatSignedPrice(0.04)).toBe("0.0");
  });

  it("signs changes both ways", () => {
    expect(formatSignedPrice(12.3)).toBe("+12.3");
    expect(formatSignedPrice(-12.3)).toBe(`${MINUS}12.3`);
  });

  it("adds the unit and joins a range", () => {
    expect(formatPriceWithUnit(63.85)).toBe("63.9 €/MWh");
    expect(formatPriceRange(-4.7, 46)).toBe(`${MINUS}4.7 to 46.0`);
  });

  it("shows a dash for missing values, never NaN", () => {
    for (const value of [null, undefined, Number.NaN, Number.POSITIVE_INFINITY]) {
      expect(formatPrice(value)).toBe(NO_VALUE);
      expect(formatSignedPrice(value)).toBe(NO_VALUE);
      expect(formatPercent(value)).toBe(NO_VALUE);
      expect(formatSignedEuro(value)).toBe(NO_VALUE);
    }
  });
});

describe("probabilities", () => {
  it("shows whole percents and never rounds a small risk down to zero", () => {
    expect(formatPercent(0.42)).toBe("42%");
    expect(formatPercent(0.003)).toBe("<1%");
    expect(formatPercent(0)).toBe("0%");
    expect(formatPercent(1)).toBe("100%");
  });

  it("gives changes in percentage points", () => {
    expect(formatPoints(0.16)).toBe("+16 pp");
    expect(formatPoints(-0.21)).toBe(`${MINUS}21 pp`);
    expect(formatPoints(0.001)).toBe("0 pp");
  });
});

describe("money, power and spans", () => {
  it("rounds euros to whole units", () => {
    expect(formatSignedEuro(1240.4)).toBe("+€1,240");
    expect(formatSignedEuro(-1240.4)).toBe(`${MINUS}€1,240`);
    expect(formatSignedEuro(-0.2)).toBe("€0");
  });

  it("drops needless decimals on megawatts", () => {
    expect(formatMegawatts(5)).toBe("5 MW");
    expect(formatMegawatts(2.5)).toBe("2.5 MW");
  });

  it("reads minutes the way a person says them", () => {
    expect(formatMinutes(75)).toBe("1 h 15 min");
    expect(formatMinutes(45)).toBe("45 min");
    expect(formatMinutes(120)).toBe("2 h");
    expect(formatMinutes(null)).toBe(NO_VALUE);
  });
});

describe("scores", () => {
  it("keeps the requested decimals", () => {
    expect(formatScore(43.3952)).toBe("43.40");
    expect(formatScore(0.4183, 3)).toBe("0.418");
  });

  it("says better or worse where lower is better", () => {
    expect(formatBetter(43.4, 66.2)).toBe("34% better");
    expect(formatBetter(70, 66.2)).toBe("6% worse");
    expect(formatBetter(66.2, 66.2)).toBe("No better");
    expect(formatBetter(null, 66.2)).toBe(NO_VALUE);
  });
});

describe("API time", () => {
  it("is always the strict UTC form with no fractions", () => {
    expect(toApiTime("2026-10-23T07:00:00.000Z")).toBe("2026-10-23T07:00:00Z");
    expect(toApiTime(new Date("2026-10-23T10:00:00+03:00"))).toBe("2026-10-23T07:00:00Z");
    expect(toApiTime("2026-10-23T07:00:00.000Z")).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/);
  });

  it("does hour maths in UTC", () => {
    expect(addHours("2026-10-23T07:00:00Z", 1)).toBe("2026-10-23T08:00:00Z");
    expect(addHours("2026-10-23T07:00:00Z", -24)).toBe("2026-10-22T07:00:00Z");
    expect(floorToHour("2026-10-23T07:40:00Z")).toBe("2026-10-23T07:00:00Z");
    expect(hoursBetween("2026-10-23T07:00:00Z", "2026-10-23T09:30:00Z")).toBe(2.5);
  });

  it("converts to and from chart time", () => {
    const iso = "2026-10-23T07:15:00Z";
    expect(fromUnixSeconds(toUnixSeconds(iso))).toBe(iso);
  });
});

describe("time on screen", () => {
  it("reads UTC in every season", () => {
    expect(formatClock("2026-10-23T13:00:00Z")).toBe("13:00");
    expect(formatClock("2026-10-26T13:00:00Z")).toBe("13:00");
  });

  it("names the UTC day, even when Helsinki is already on the next one", () => {
    expect(formatDate("2026-10-22T22:00:00Z")).toBe("Thu 22 Oct");
    expect(formatDateTime("2026-10-22T22:00:00Z")).toBe("Thu 22 Oct 22:00");
    expect(formatShortDateTime("2026-10-22T22:00:00Z")).toBe("22 Oct 22:00");
    expect(utcHour("2026-10-22T22:00:00Z")).toBe(22);
    expect(toCalendarDate("2026-10-22T22:00:00Z").getDate()).toBe(22);
  });

  it("names the zone in text read on its own", () => {
    expect(formatDateTimeUtc("2026-10-23T09:00:00Z")).toBe("Fri 23 Oct 09:00 UTC");
    expect(formatClockUtc("2026-10-23T09:00:00Z")).toBe("09:00 UTC");
  });

  it("has no repeated hour when the clocks go back on 25 Oct", () => {
    expect(formatClock("2026-10-25T00:15:00Z")).toBe("00:15");
    expect(formatClock("2026-10-25T01:15:00Z")).toBe("01:15");
  });

  it("keeps a window short unless it crosses midnight", () => {
    expect(formatWindow("2026-10-23T13:00:00Z", "2026-10-23T15:00:00Z")).toBe("13:00–15:00");
    expect(formatWindow("2026-10-23T22:00:00Z", "2026-10-24T00:00:00Z")).toBe("22:00–00:00");
    expect(formatWindow("2026-10-23T23:00:00Z", "2026-10-24T02:00:00Z")).toBe("Fri 23:00–Sat 02:00");
  });

  it("names a window's day once", () => {
    expect(formatWindowWithDay("2026-10-23T13:00:00Z", "2026-10-23T15:00:00Z")).toBe("Fri 13:00–15:00");
    expect(formatWindowWithDay("2026-10-23T22:00:00Z", "2026-10-24T00:00:00Z")).toBe("Fri 22:00–00:00");
    expect(formatWindowWithDay("2026-10-23T23:00:00Z", "2026-10-24T02:00:00Z")).toBe("Fri 23:00–Sat 02:00");
  });

  it("round-trips a date and hour through the viewing-time picker", () => {
    const iso = "2026-10-22T22:00:00Z";
    expect(fromUtcDate(toCalendarDate(iso), utcHour(iso))).toBe(iso);
  });

  it("has every hour once on the day the clocks change", () => {
    const day = new Date(2026, 9, 25);
    expect(fromUtcDate(day, 0)).toBe("2026-10-25T00:00:00Z");
    expect(fromUtcDate(day, 1)).toBe("2026-10-25T01:00:00Z");
    expect(fromUtcDate(day, 23)).toBe("2026-10-25T23:00:00Z");
  });
});
