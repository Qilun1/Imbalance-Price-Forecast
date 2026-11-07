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
const HISTORY_HOURS = 24;
export const HORIZON_HOURS = 10;

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
  /** The day before the viewing time, for the left side of the forecast chart. */
  recentActuals: (origin: string, asOf?: string) =>
    queryOptions({
      queryKey: ["actuals", "recent", asOf ?? "latest", origin],
      queryFn: () => api.actuals(asOf, addHours(origin, -HISTORY_HOURS), origin),
      ...byTime(asOf),
    }),
  /** What really happened after the viewing time. Asked of the newest data on purpose: it is hindsight. */
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
};
