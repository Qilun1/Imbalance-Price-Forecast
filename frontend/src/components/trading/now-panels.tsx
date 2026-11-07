"use client";

import { useQuery } from "@tanstack/react-query";
import { CircleDashed, History, ListX } from "lucide-react";
import dynamic from "next/dynamic";
import { useMemo, useState } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ActualPoint, Changes, Forecast } from "@/lib/api/client";
import { queries } from "@/lib/api/queries";
import {
  formatClock,
  formatDateTime,
  formatPercent,
  formatPoints,
  formatPrice,
  formatPriceRange,
  formatSignedPrice,
  formatWindow,
  PRICE_UNIT,
} from "@/lib/format";
import { headline, isInWindow, rankDrivers, stepsInWindow, windowOf } from "@/lib/forecast";
import { useViewingTime } from "@/lib/realtime/viewing-time";

import { DirectionLabel, Unit } from "./cells";
import { KpiCard, KpiCardSkeleton } from "./kpi-card";
import { isSameSituation, useNow } from "./now-context";
import { Panel, PanelBody, PanelHeader, PanelMessage, SkeletonLines } from "./panel";
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

function Scope() {
  const { selected } = useNow();
  return selected ? `for ${formatWindow(selected.window_start_utc, selected.window_end_utc)}` : "across the next 10 hours";
}

function DriverRows({ forecast }: { forecast: Forecast }) {
  const { selected } = useNow();
  const steps = stepsInWindow(forecast.steps, selected ? windowOf(selected) : null);
  const drivers = rankDrivers(steps.length ? steps : forecast.steps, 5);
  const total = steps.length || forecast.steps.length;
  if (!drivers.length) {
    return (
      <PanelMessage icon={ListX} title="No drivers named">
        This forecast names no main factors for this window.
      </PanelMessage>
    );
  }
  return (
    <ol className="flex flex-col gap-2">
      {drivers.map((driver) => (
        <li key={driver.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-3 gap-y-1">
          <span className="truncate text-sm text-ink" title={driver.label}>
            {driver.label}
          </span>
          <span className="text-xs text-muted-foreground">
            {driver.quarters} of {total} quarter-hours
          </span>
          <span className="col-span-2 h-1 overflow-hidden rounded-full bg-fill" aria-hidden>
            <span className="block h-full rounded-full bg-series-1" style={{ width: `${(driver.quarters / total) * 100}%` }} />
          </span>
        </li>
      ))}
    </ol>
  );
}

export function DriversPanel() {
  const { asOf } = useViewingTime();
  const forecast = useQuery(queries.forecast(asOf));
  return (
    <Panel label="Main factors" className="h-full">
      <PanelHeader title="Main factors" note={<Scope />} />
      <PanelBody className="scrollbar-thin overflow-auto">
        <QueryState query={forecast} skeleton={<SkeletonLines rows={5} />}>
          {(data) => <DriverRows forecast={data} />}
        </QueryState>
      </PanelBody>
    </Panel>
  );
}

function ChangeRows({ changes }: { changes: Changes }) {
  const { selected } = useNow();
  if (!changes.previous_origin_utc) {
    return (
      <PanelMessage icon={History} title="No previous update">
        This is the first forecast of its period, so there is nothing to compare with.
      </PanelMessage>
    );
  }
  if (!changes.points.length) {
    return (
      <PanelMessage icon={History} title="No changes to show">
        The previous update covers no quarter-hours of this one.
      </PanelMessage>
    );
  }
  const inScope = selected ? changes.points.filter((point) => isInWindow(point.delivery_start_utc, windowOf(selected))) : changes.points;
  const largest = [...(inScope.length ? inScope : changes.points)]
    .sort((a, b) => Math.abs(b.p50_change) - Math.abs(a.p50_change))
    .slice(0, 3)
    .sort((a, b) => a.delivery_start_utc.localeCompare(b.delivery_start_utc));
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Time</TableHead>
          <TableHead className="text-right">P50 change</TableHead>
          <TableHead className="text-right">High risk</TableHead>
          <TableHead className="text-right">Low risk</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {largest.map((point) => (
          <TableRow key={point.delivery_start_utc}>
            <TableCell>{formatClock(point.delivery_start_utc)}</TableCell>
            <TableCell className="text-right font-medium">{formatSignedPrice(point.p50_change)}</TableCell>
            <TableCell className="text-right">{formatPoints(point.p_spike_high_change)}</TableCell>
            <TableCell className="text-right">{formatPoints(point.p_spike_low_change)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function ChangesPanel() {
  const { asOf } = useViewingTime();
  const changes = useQuery(queries.changes(asOf));
  const since = changes.data?.previous_origin_utc;
  return (
    <Panel label="Changes since the previous update" className="h-full">
      <PanelHeader title="Largest changes" note={since ? `since ${formatDateTime(since)}` : undefined} />
      <PanelBody className="scrollbar-thin overflow-auto px-1 pb-1">
        <QueryState query={changes} skeleton={<SkeletonLines rows={4} className="px-3" />}>
          {(data) => <ChangeRows changes={data} />}
        </QueryState>
      </PanelBody>
    </Panel>
  );
}
