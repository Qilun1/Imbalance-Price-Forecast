"use client";

import { useQuery } from "@tanstack/react-query";
import { Check, Eye, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import type { Alert, AlertKind } from "@/lib/api/client";
import { queries } from "@/lib/api/queries";
import { formatWindow } from "@/lib/format";
import { useViewingTime } from "@/lib/realtime/viewing-time";
import { cn } from "@/lib/utils";

import { isSameSituation, useNow } from "./now-context";
import { Panel, PanelBody, PanelHeader, PanelMessage } from "./panel";
import { PriceHistorySection } from "./price-history";
import { QueryState } from "./query-state";

export const KIND_LABELS: Record<AlertKind, string> = {
  spike_risk: "Exceptional price risk",
  regulation_expected: "Regulation expected",
  forecast_changed: "Forecast changed",
  conflicting_signals: "Signals disagree",
  high_uncertainty: "High uncertainty",
  stale_data: "Stale data",
  expert_review: "Expert review",
};

export function SeverityBadge({ severity }: { severity: Alert["severity"] }) {
  return severity === "review" ? (
    <Badge variant="error">
      <TriangleAlert aria-hidden />
      Review
    </Badge>
  ) : (
    <Badge variant="warning">
      <Eye aria-hidden />
      Watch
    </Badge>
  );
}

function SituationCard({ alert, selected }: { alert: Alert; selected: boolean }) {
  const { select, review } = useNow();
  return (
    <article className={cn("rounded-md border", selected ? "border-stone" : "border-hairline-soft hover:bg-fill/60")}>
      <button type="button" aria-pressed={selected} onClick={() => select(alert)} className="flex w-full flex-col gap-1 rounded-md px-3 py-2.5 text-left">
        <span className="flex items-center justify-between gap-2">
          <SeverityBadge severity={alert.severity} />
          <span className="text-sm font-medium text-ink">{formatWindow(alert.window_start_utc, alert.window_end_utc)}</span>
        </span>
        <span className="text-base font-medium text-ink">{alert.title}</span>
        {selected ? <span className="text-sm text-stone">{alert.message}</span> : null}
      </button>
      {selected ? (
        <div className="px-3 pb-3">
          <Button variant="primary" size="sm" onClick={() => review(alert)}>
            Review situation
          </Button>
        </div>
      ) : null}
    </article>
  );
}

/** `top` replaces the price history above the situations, as the Naantali CHP screen does with its tabs. */
export function SituationsPanel({ top = <PriceHistorySection /> }: { top?: ReactNode }) {
  const { asOf } = useViewingTime();
  const query = useQuery(queries.alerts(asOf));
  const { alerts, selected } = useNow();
  return (
    <Panel label="Price history and what to check now" className="h-full">
      {top}
      <PanelHeader title="What to check now" level={1} highlight note={alerts.length ? `${alerts.length} now` : undefined} />
      <PanelBody className="px-0 pb-0">
        <QueryState
          query={query}
          isEmpty={(data) => data.alerts.length === 0}
          empty={
            <PanelMessage icon={Check} title="Nothing to check">
              No situation stands out in the next 10 hours. The forecast updates every hour.
            </PanelMessage>
          }
          skeleton={
            <div className="flex flex-col gap-2 px-4" aria-hidden>
              {[0, 1, 2].map((key) => (
                <Skeleton key={key} className="h-16 w-full" />
              ))}
            </div>
          }
        >
          {() => (
            <ScrollArea className="h-full">
              <ul className="flex flex-col gap-2 px-4 pb-4">
                {alerts.map((alert) => (
                  <li key={`${alert.kind}|${alert.title}|${alert.window_start_utc}`}>
                    <SituationCard alert={alert} selected={isSameSituation(alert, selected)} />
                  </li>
                ))}
              </ul>
            </ScrollArea>
          )}
        </QueryState>
      </PanelBody>
    </Panel>
  );
}
