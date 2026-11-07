"use client";

import { useQuery } from "@tanstack/react-query";
import { createContext, type ReactNode, use, useMemo, useState } from "react";

import type { Alert } from "@/lib/api/client";
import { queries } from "@/lib/api/queries";
import { useViewingTime } from "@/lib/realtime/viewing-time";

const keyOf = (alert: Alert) => `${alert.kind}|${alert.title}|${alert.window_start_utc}`;

type NowState = {
  alerts: readonly Alert[];
  /** The situation in focus: the viewer's pick, or the most serious one. */
  selected: Alert | null;
  reviewing: Alert | null;
  select: (alert: Alert) => void;
  review: (alert: Alert | null) => void;
};

const Context = createContext<NowState | null>(null);

const NONE: readonly Alert[] = [];

/** Selecting a situation highlights its window in the chart on the Now screen. */
export function NowProvider({ children }: { children: ReactNode }) {
  const { asOf } = useViewingTime();
  const { data } = useQuery(queries.alerts(asOf));
  const alerts = data?.alerts ?? NONE;
  const [pickedKey, setPickedKey] = useState<string | null>(null);
  const [reviewing, review] = useState<Alert | null>(null);

  const value = useMemo<NowState>(() => {
    const picked = alerts.find((alert) => keyOf(alert) === pickedKey);
    return {
      alerts,
      selected: picked ?? alerts[0] ?? null,
      reviewing,
      select: (alert) => setPickedKey(keyOf(alert)),
      review,
    };
  }, [alerts, pickedKey, reviewing]);

  return <Context value={value}>{children}</Context>;
}

export function useNow() {
  const value = use(Context);
  if (!value) throw new Error("useNow needs a NowProvider");
  return value;
}

export function isSameSituation(a: Alert | null, b: Alert | null): boolean {
  return a !== null && b !== null && keyOf(a) === keyOf(b);
}
