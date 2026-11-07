"use client";

/**
 * The viewing time: the moment the whole dashboard shows. It lives in the URL as ?as_of=<UTC>, so it
 * carries across screens and can be shared. No value means "follow the newest forecast".
 * This is the one place that knows how it is stored.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { createContext, type ReactNode, use, useCallback, useEffect, useMemo, useState } from "react";

import { queries } from "@/lib/api/queries";
import { addHours, floorToHour, hoursBetween } from "@/lib/format";

type ViewingTimeState = {
  /** Sent to the API. Undefined while following the newest forecast. */
  asOf: string | undefined;
  /** The moment on screen, once the range is known. */
  current: string | undefined;
  first: string | undefined;
  last: string | undefined;
  isPast: boolean;
};

type ViewingTimeActions = {
  replaying: boolean;
  toggleReplay: () => void;
  setTime: (moment: string | undefined) => void;
  step: (hours: number) => void;
  canStep: (hours: number) => boolean;
  toLatest: () => void;
};

const Context = createContext<(ViewingTimeState & ViewingTimeActions) | null>(null);

/** One forecast hour per beat, slow enough to read what changed. */
const REPLAY_MS = 1800;

/** React learns of a URL change a moment later, so a held key must read the URL itself. */
function readUrl(): string | undefined {
  return new URL(window.location.href).searchParams.get("as_of") ?? undefined;
}

function writeUrl(asOf: string | undefined): void {
  const url = new URL(window.location.href);
  if (asOf) url.searchParams.set("as_of", asOf);
  else url.searchParams.delete("as_of");
  // A shallow URL change: Next keeps useSearchParams in sync without asking the server for the page.
  window.history.replaceState(null, "", url);
}

export function ViewingTimeProvider({ children }: { children: ReactNode }) {
  const searchParams = useSearchParams();
  const { data: meta } = useQuery(queries.meta());
  const requested = searchParams.get("as_of") ?? undefined;
  const first = meta?.first_origin_utc;
  const last = meta?.last_origin_utc;
  const current = requested ?? last;

  const setTime = useCallback(
    (moment: string | undefined) => {
      if (moment === undefined || last === undefined || first === undefined) return writeUrl(moment);
      const hour = floorToHour(moment);
      if (hoursBetween(hour, last) <= 0) return writeUrl(undefined);
      writeUrl(hoursBetween(first, hour) < 0 ? first : hour);
    },
    [first, last],
  );

  const canStep = useCallback(
    (hours: number) => {
      if (current === undefined || first === undefined || last === undefined) return false;
      return hours < 0 ? hoursBetween(first, current) > 0 : hoursBetween(current, last) > 0;
    },
    [current, first, last],
  );

  const step = useCallback(
    (hours: number) => {
      const from = readUrl() ?? last;
      if (from !== undefined) setTime(addHours(floorToHour(from), hours));
    },
    [last, setTime],
  );

  const toLatest = useCallback(() => writeUrl(undefined), []);

  // A past answer never changes, so fetching the next hours ahead makes stepping feel instant.
  const queryClient = useQueryClient();
  useEffect(() => {
    if (!requested) return;
    for (const hours of [-1, 1, 2]) {
      const moment = addHours(floorToHour(requested), hours);
      if (first === undefined || last === undefined) continue;
      if (hoursBetween(first, moment) < 0 || hoursBetween(moment, last) <= 0) continue;
      void queryClient.prefetchQuery(queries.forecast(moment));
      void queryClient.prefetchQuery(queries.changes(moment));
      void queryClient.prefetchQuery(queries.alerts(moment));
    }
  }, [requested, first, last, queryClient]);

  const [wantsReplay, setWantsReplay] = useState(false);
  const replaying = wantsReplay && canStep(1);
  useEffect(() => {
    if (!replaying) return;
    const timer = setInterval(() => step(1), REPLAY_MS);
    return () => clearInterval(timer);
  }, [replaying, step]);
  const toggleReplay = useCallback(() => setWantsReplay((playing) => !playing), []);

  const value = useMemo(
    () => ({
      asOf: requested,
      current,
      first,
      last,
      isPast: requested !== undefined,
      replaying,
      toggleReplay,
      setTime,
      step,
      canStep,
      toLatest,
    }),
    [requested, current, first, last, replaying, toggleReplay, setTime, step, canStep, toLatest],
  );

  return <Context value={value}>{children}</Context>;
}

export function useViewingTime() {
  const value = use(Context);
  if (!value) throw new Error("useViewingTime needs a ViewingTimeProvider");
  return value;
}
