/**
 * Query definitions. A past viewing time never changes, so its answers stay fresh for good. The newest
 * view refetches when /api/meta reports a new forecast (see lib/realtime/connection.ts).
 * Spot prices stay in memory: the query cache is never written to browser storage (AGENTS.md rule 6).
 */
import { keepPreviousData, queryOptions } from "@tanstack/react-query";

import { addHours } from "@/lib/format";

import { api } from "./client";
import { ApiError } from "./errors";

const THIRTY_MINUTES = 30 * 60_000;
const META_POLL_MS = 60_000;
const META_RETRY_MS = 10_000;
export const HORIZON_HOURS = 10;
/** First quarter-hour of the organiser's data (package README, AGENTS.md section 4). */
export const DATA_START_UTC = "2026-05-31T21:00:00Z";
/** Day-ahead spot reaches at most this far past the forecast time. The API drops what was not yet published. */
const DAY_AHEAD_HOURS = 48;

const byTime = (asOf: string | undefined) => ({
  staleTime: asOf ? Number.POSITIVE_INFINITY : META_POLL_MS,
  gcTime: THIRTY_MINUTES,
  placeholderData: keepPreviousData,
});

export function shouldRetry(failures: number, error: unknown): boolean {
  return error instanceof ApiError && error.isConnectionProblem && failures < 1;
}

export const queries = {
  meta: () =>
    queryOptions({
      queryKey: ["meta"],
      queryFn: api.meta,
      staleTime: META_POLL_MS,
      refetchInterval: (query) => (query.state.status === "error" ? META_RETRY_MS : META_POLL_MS),
      refetchIntervalInBackground: false,
      retry: 1,
      retryDelay: 1000,
    }),
  forecast: (asOf?: string) =>
    queryOptions({ queryKey: ["forecast", asOf ?? "latest"], queryFn: () => api.forecast(asOf), ...byTime(asOf) }),
  changes: (asOf?: string) =>
    queryOptions({ queryKey: ["changes", asOf ?? "latest"], queryFn: () => api.changes(asOf), ...byTime(asOf) }),
  alerts: (asOf?: string) =>
    queryOptions({ queryKey: ["alerts", asOf ?? "latest"], queryFn: () => api.alerts(asOf), ...byTime(asOf) }),
  alertHistory: (asOf?: string) =>
    queryOptions({ queryKey: ["alert-history", asOf ?? "latest"], queryFn: () => api.alertHistory(asOf), ...byTime(asOf) }),
  /** Everything from the start of the data, plus day-ahead spot already published. Usable rows only (rule 4). */
  priceHistory: (origin: string, asOf?: string) =>
    queryOptions({
      queryKey: ["actuals", "all", asOf ?? "latest", origin],
      queryFn: () => api.actuals(asOf, DATA_START_UTC, addHours(origin, DAY_AHEAD_HOURS)),
      ...byTime(asOf),
    }),
  /** Observed prices, spot included, for quarter-hours in [from, to), as usable at the viewing time (rule 4). */
  actualsBetween: (asOf: string | undefined, from: string, to: string) =>
    queryOptions({
      queryKey: ["actuals", "between", asOf ?? "latest", from, to],
      queryFn: () => api.actuals(asOf, from, to),
      ...byTime(asOf),
    }),
  /** What really happened after the viewing time. Asked without a viewing time on purpose: it is hindsight. Ends before the test period. */
  outcome: (origin: string) =>
    queryOptions({
      queryKey: ["actuals", "outcome", origin],
      queryFn: () => api.actuals(undefined, origin, addHours(origin, HORIZON_HOURS)),
      staleTime: Number.POSITIVE_INFINITY,
      gcTime: THIRTY_MINUTES,
    }),
  performance: (asOf: string | undefined, from: string, to: string) =>
    queryOptions({
      queryKey: ["performance", asOf ?? "latest", from, to],
      queryFn: () => api.performance(asOf, from, to),
      ...byTime(asOf),
    }),
  hindsight: (asOf: string | undefined, from: string, to: string, leadHours: number) =>
    queryOptions({
      queryKey: ["hindsight", asOf ?? "latest", from, to, leadHours],
      queryFn: () => api.hindsight(asOf, from, to, leadHours),
      ...byTime(asOf),
    }),
  /** The plant operator's event notes (CHP with electric boilers). */
  operatorNotes: (asOf?: string) =>
    queryOptions({ queryKey: ["notes", "operator", asOf ?? "latest"], queryFn: () => api.notes(asOf, "operator"), ...byTime(asOf) }),
  /** Every outage message, however small, in the forecast's 10 hours. */
  umm: (asOf?: string) =>
    queryOptions({ queryKey: ["umm", asOf ?? "latest"], queryFn: () => api.umm(asOf, HORIZON_HOURS, 0), ...byTime(asOf) }),
  /** Monthly statistics: the API caches them for a day, so an hour here is plenty. Not tied to the viewing time. */
  fuel: () => queryOptions({ queryKey: ["fuel"], queryFn: api.fuel, staleTime: 60 * 60_000, gcTime: THIRTY_MINUTES }),
};
