"use client";

import { useQuery } from "@tanstack/react-query";
import { CircleDashed } from "lucide-react";
import dynamic from "next/dynamic";
import { useMemo, useState } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import type { ActualPoint } from "@/lib/api/client";
import { queries } from "@/lib/api/queries";
import { formatClock, formatPercent, formatPrice, formatPriceRange, formatSignedPrice, PRICE_UNIT } from "@/lib/format";
import { headline, windowOf } from "@/lib/forecast";
import { useViewingTime } from "@/lib/realtime/viewing-time";

import { DirectionLabel, Unit } from "./cells";
import { KpiCard, KpiCardSkeleton } from "./kpi-card";
import { isSameSituation, useNow } from "./now-context";
import { Panel, PanelBody, PanelHeader, PanelMessage } from "./panel";
import { QueryState } from "./query-state";

const NONE: readonly ActualPoint[] = [];

const ChartSkeleton = () => <Skeleton className="h-full min-h-56 w-full" />;

const ForecastChart = dynamic(() => import("./forecast-chart"), { ssr: false, loading: ChartSkeleton });

const KPI_LABELS = ["Next hour price", "High price risk", "Low price risk", "Direction next hour", "Largest revision"] as const;

export function KpiRow() {
  const { asOf } = useViewingTime();
  const forecast = useQuery(queries.forecast(asOf));
  const changes = useQuery(queries.changes(asOf));
  const top = forecast.data ? headline(forecast.data, changes.data) : null;
  const [nextHour, high, low, direction, revision] = KPI_LABELS;

  if ((forecast.isError && !forecast.data) || (forecast.data && !top)) return null;
  if (!top) {
    return (
      <div className="grid shrink-0 grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5" aria-hidden>
        {KPI_LABELS.map((label) => (
          <KpiCardSkeleton key={label} label={label} />
        ))}
      </div>
    );
  }
  return (
    <div className="grid shrink-0 grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
      <KpiCard
        label={nextHour}
        value={formatPrice(top.nextHour.p50)}
        unit={<Unit />}
        detail={`P10–P90 ${formatPriceRange(top.nextHour.p10, top.nextHour.p90)}`}
      />
      <KpiCard label={high} value={formatPercent(top.highRisk.probability)} detail={`Highest at ${formatClock(top.highRisk.at)}`} />
      <KpiCard label={low} value={formatPercent(top.lowRisk.probability)} detail={`Highest at ${formatClock(top.lowRisk.at)}`} />
      <KpiCard
        label={direction}
        value={<DirectionLabel direction={top.direction.direction} className="[&_svg]:size-5" />}
        detail={`On average ${formatPercent(top.direction.probability)} likely`}
      />
      <KpiCard
        label={revision}
        value={top.revision ? formatSignedPrice(top.revision.change) : "None"}
        unit={top.revision ? <Unit /> : undefined}
        detail={top.revision ? `For ${formatClock(top.revision.at)}, since ${formatClock(top.revision.since)}` : "No previous update"}
      />
    </div>
  );
}

export function ForecastPanel() {
  const { asOf, isPast } = useViewingTime();
  const forecast = useQuery(queries.forecast(asOf));
  const { data: meta } = useQuery(queries.meta());
  const { alerts, selected } = useNow();
  const origin = forecast.data?.origin_utc;
  const history = useQuery({ ...queries.recentActuals(origin ?? "", asOf), enabled: origin !== undefined });
  const [wantsOutcome, setWantsOutcome] = useState(false);
  const showOutcome = wantsOutcome && isPast && origin !== undefined;
  const outcome = useQuery({ ...queries.outcome(origin ?? ""), enabled: showOutcome });

  const windows = useMemo(
    () =>
      alerts
        .filter((alert) => alert.kind !== "stale_data")
        .map((alert) => ({ ...windowOf(alert), selected: isSameSituation(alert, selected) })),
    [alerts, selected],
  );

  return (
    <Panel label="Forecast for the next 10 hours" className="h-full">
      <PanelHeader
        title="Next 10 hours"
        note={
          showOutcome
            ? "The black line after the forecast time was not known then"
            : `${PRICE_UNIT}, band P10–P90, grey zone spot ± ${meta?.spike_margin_eur_mwh ?? 50}, times in UTC`
        }
      >
        {isPast ? (
          <div className="flex items-center gap-2">
            <Switch id="show-outcome" size="sm" checked={wantsOutcome} onCheckedChange={setWantsOutcome} />
            <Label htmlFor="show-outcome" className="text-xs font-medium">
              Show what happened
            </Label>
          </div>
        ) : null}
      </PanelHeader>
      <PanelBody>
        <QueryState
          query={forecast}
          isEmpty={(data) => data.steps.length === 0}
          empty={
            <PanelMessage icon={CircleDashed} title="No forecast at this time">
              Step to another hour, or go back to the latest forecast.
            </PanelMessage>
          }
          skeleton={<ChartSkeleton />}
        >
          {(data) => (
            <ForecastChart
              forecast={data}
              history={history.data?.points ?? NONE}
              outcome={showOutcome ? (outcome.data?.points ?? NONE) : NONE}
              margin={meta?.spike_margin_eur_mwh ?? 50}
              windows={windows}
            />
          )}
        </QueryState>
      </PanelBody>
    </Panel>
  );
}
