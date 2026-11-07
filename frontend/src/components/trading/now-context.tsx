"use client";

import { useQuery } from "@tanstack/react-query";
import { createContext, type ReactNode, use, useMemo, useState } from "react";

import type { Alert } from "@/lib/api/client";
import { queries } from "@/lib/api/queries";
import type { Figure } from "@/lib/forecast";
import { useViewingTime } from "@/lib/realtime/viewing-time";

const keyOf = (alert: Alert) => `${alert.kind}|${alert.title}|${alert.window_start_utc}`;

type NowState = {
  alerts: readonly Alert[];
  /** The situation in focus: the viewer's pick, or the most serious one. */
  selected: Alert | null;
  reviewing: Alert | null;
  /** The key figure shown in the chart, if one was picked. It takes over the chart's shading. */
  figure: Figure | null;
  select: (alert: Alert) => void;
  review: (alert: Alert | null) => void;
  /** Picking the figure already shown, or null, shows none. */
  showFigure: (figure: Figure | null) => void;
};

const Context = createContext<NowState | null>(null);

const NONE: readonly Alert[] = [];

/**
 * Selecting a situation highlights its window in the chart on the Now screen, and so does a key figure.
 * One at a time: picking a situation puts the figure away.
 */
export function NowProvider({ children }: { children: ReactNode }) {
  const { asOf } = useViewingTime();
  const { data } = useQuery(queries.alerts(asOf));
  const alerts = data?.alerts ?? NONE;
  const [pickedKey, setPickedKey] = useState<string | null>(null);
  const [reviewing, review] = useState<Alert | null>(null);
  const [figure, setFigure] = useState<Figure | null>(null);

  const value = useMemo<NowState>(() => {
    const picked = alerts.find((alert) => keyOf(alert) === pickedKey);
    return {
      alerts,
      selected: picked ?? alerts[0] ?? null,
      reviewing,
      figure,
      select: (alert) => {
        setPickedKey(keyOf(alert));
        setFigure(null);
      },
      review,
      showFigure: (next) => setFigure((current) => (next === current ? null : next)),
    };
  }, [alerts, pickedKey, reviewing, figure]);

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
