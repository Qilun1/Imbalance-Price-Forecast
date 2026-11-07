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
import { formatClock, formatEuro, formatPercent, PRICE_UNIT } from "@/lib/format";
import { headline, windowOf } from "@/lib/forecast";
import { useViewingTime } from "@/lib/realtime/viewing-time";

import { DirectionLabel } from "./cells";
import { Choice } from "./choice";
import { isSameSituation, useNow } from "./now-context";
import { Panel, PanelBody, PanelHeader, PanelMessage } from "./panel";
import { QueryState } from "./query-state";
import { Euro, Stat, StatStrip, StatStripSkeleton } from "./stat-strip";

const NONE: readonly ActualPoint[] = [];

const ChartSkeleton = () => <Skeleton className="h-full min-h-56 w-full" />;

const ForecastChart = dynamic(() => import("./forecast-chart"), { ssr: false, loading: ChartSkeleton });

const KPI_LABELS = ["Next hour price", "Highest price", "Lowest price", "Direction next hour", "Largest revision"] as const;

export function KpiRow() {
  const { asOf } = useViewingTime();
  const forecast = useQuery(queries.forecast(asOf));
  const changes = useQuery(queries.changes(asOf));
  const top = forecast.data ? headline(forecast.data, changes.data) : null;
  const [nextHour, highest, lowest, direction, revision] = KPI_LABELS;

  if ((forecast.isError && !forecast.data) || (forecast.data && !top)) return null;
  if (!top) {
    return <StatStripSkeleton labels={KPI_LABELS} />;
  }
  const change = top.revision?.change ?? 0;
  return (
    <StatStrip label="Key figures">
      <Stat
        label={nextHour}
        value={<Euro value={top.nextHour.p50} />}
        detail={`Likely ${formatEuro(top.nextHour.p10, { digits: 0 })} to ${formatEuro(top.nextHour.p90, { digits: 0 })}`}
      />
      <Stat label={highest} value={<Euro value={top.highest.price} />} detail={`At ${formatClock(top.highest.at)}`} />
      <Stat label={lowest} value={<Euro value={top.lowest.price} />} detail={`At ${formatClock(top.lowest.at)}`} />
      <Stat
        label={direction}
        value={<DirectionLabel direction={top.direction.direction} className="[&_svg]:size-4" />}
        detail={`${formatPercent(top.direction.probability)} likely`}
      />
      <Stat
        label={revision}
        value={top.revision ? <Euro value={change} plus /> : "None"}
        tone={change > 0 ? "text-up" : change < 0 ? "text-down" : undefined}
        detail={top.revision ? `${formatClock(top.revision.at)}, since ${formatClock(top.revision.since)}` : "No previous update"}
      />
    </StatStrip>
  );
}

/** How much history is in view next to the forecast. The rest is a drag away. */
const SPANS = [
  { value: "1d", label: "1 day", hours: 24 },
  { value: "3d", label: "3 days", hours: 72 },
  { value: "1w", label: "1 week", hours: 168 },
  { value: "1m", label: "1 month", hours: 720 },
  { value: "3m", label: "3 months", hours: 2160 },
  { value: "all", label: "All", hours: null },
] as const;
type Span = (typeof SPANS)[number]["value"];

export function ForecastPanel() {
  const { asOf, isPast } = useViewingTime();
  const forecast = useQuery(queries.forecast(asOf));
  const { data: meta } = useQuery(queries.meta());
  const { alerts, selected } = useNow();
  const origin = forecast.data?.origin_utc;
  // All history since the data starts: the same request as the price history table.
  const history = useQuery({ ...queries.priceHistory(origin ?? "", asOf), enabled: origin !== undefined });
  // Only the past here: spot for the forecast hours comes with the forecast itself.
  const past = useMemo(
    () => (origin && history.data ? history.data.points.filter((point) => point.delivery_start_utc < origin) : NONE),
    [history.data, origin],
  );
  const [wantsOutcome, setWantsOutcome] = useState(false);
  const [span, setSpan] = useState<Span>("1d");
  const spanHours = SPANS.find((option) => option.value === span)?.hours ?? null;
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
    <Panel label="Imbalance price and forecast" className="h-full">
      <PanelHeader
        title="Imbalance price and forecast"
        note={`${PRICE_UNIT}, shaded band is the likely range (P10–P90)`}
        oneRow
      >
        {isPast ? (
          <div className="flex shrink-0 items-center gap-2">
            <Switch id="show-outcome" size="sm" checked={wantsOutcome} onCheckedChange={setWantsOutcome} />
            <Label htmlFor="show-outcome" className="text-xs font-medium">
              Show what happened
            </Label>
          </div>
        ) : null}
      </PanelHeader>
      <PanelBody className="pb-2">
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
              history={past}
              outcome={showOutcome ? (outcome.data?.points ?? NONE) : NONE}
              margin={meta?.spike_margin_eur_mwh ?? 50}
              windows={windows}
              spanHours={spanHours}
            />
          )}
        </QueryState>
      </PanelBody>
      <div className="flex shrink-0 items-center gap-3 border-t border-hairline-soft px-4 py-2">
        <span className="shrink-0 text-xs text-muted-foreground">History</span>
        <Choice label="History shown" value={span} options={SPANS} onChange={setSpan} fill />
      </div>
    </Panel>
  );
}
