"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCheck, CircleDashed, FileCheck } from "lucide-react";
import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { useMemo } from "react";
import { useDefaultLayout } from "react-resizable-panels";

import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ActualPoint, Performance, Scores } from "@/lib/api/client";
import { queries } from "@/lib/api/queries";
import { safeStorage, useIsWide } from "@/lib/browser";
import { addHours, formatBetter, formatCount, formatPercent, formatScore, hoursBetween, NO_VALUE, PRICE_UNIT } from "@/lib/format";
import { useViewingTime } from "@/lib/realtime/viewing-time";

import { Choice } from "./choice";
import { Panel, PanelBody, PanelHeader, PanelMessage, SkeletonLines } from "./panel";
import { QueryState } from "./query-state";
import { SituationLog } from "./situation-log";
import { Euro, Stat, StatStrip, StatStripSkeleton } from "./stat-strip";

const HindsightChart = dynamic(() => import("./hindsight-chart"), {
  ssr: false,
  loading: () => <Skeleton className="h-full min-h-48 w-full" />,
});

const RANGES = {
  day: { label: "Previous day", title: "Previous Day", hours: 24 },
  week: { label: "Previous week", title: "Previous Week", hours: 24 * 7 },
  month: { label: "Previous month", title: "Previous Month", hours: 24 * 30 },
} as const;
type Range = keyof typeof RANGES;

/** The chart compares the forecast made this many hours before each quarter-hour. */
const LEAD_HOURS = 1;

const NO_ACTUALS: readonly ActualPoint[] = [];

const GAP_HANDLE = "w-3 bg-transparent aria-[orientation=horizontal]:h-3 aria-[orientation=horizontal]:w-full";

function useUrlChoice<T extends string>(name: string, allowed: readonly T[], fallback: T): [T, (value: T) => void] {
  const searchParams = useSearchParams();
  const value = searchParams.get(name);
  const choice = allowed.find((candidate) => candidate === value) ?? fallback;
  const set = (next: T) => {
    const url = new URL(window.location.href);
    url.searchParams.set(name, next);
    window.history.replaceState(null, "", url);
  };
  return [choice, set];
}

/** `short` names the strip figure; `label` is the full name, in the official table and on hover. */
const METRICS: readonly { key: keyof Scores; label: string; short: string; digits: number; unit?: boolean }[] = [
  { key: "mae_p50", label: "Price error (MAE)", short: "Price error", digits: 2, unit: true },
  { key: "calibration_pinball_mean", label: "Uncertainty (pinball)", short: "Uncertainty", digits: 2, unit: true },
  { key: "brier_spike_mean", label: "Spike error (Brier)", short: "Spike error", digits: 3 },
  { key: "brier_direction", label: "Direction error (Brier)", short: "Direction error", digits: 3 },
];

/** Exceptional prices: imbalance price more than this far from spot (AGENTS.md rule 2; never changed). */
const SPIKE_MARGIN = 50;

/** How often each exceptional price happened in the period, against how often the model said it would. */
const SPIKES = [
  {
    side: "High",
    observed: "observed_spike_high_share",
    forecast: "forecast_spike_high_share",
    hint: `Exceptional high prices: share of quarter-hours with the imbalance price above spot + ${SPIKE_MARGIN} €/MWh, against the model's mean p_spike_high`,
  },
  {
    side: "Low",
    observed: "observed_spike_low_share",
    forecast: "forecast_spike_low_share",
    hint: `Exceptional low prices: share of quarter-hours with the imbalance price below spot − ${SPIKE_MARGIN} €/MWh, against the model's mean p_spike_low`,
  },
] as const satisfies readonly { side: string; observed: keyof Scores; forecast: keyof Scores; hint: string }[];

const COVERAGE_LABEL = "P10–P90 coverage";
const STRIP_LABELS = [...METRICS.map((metric) => metric.short), ...SPIKES.map(({ side }) => `${side} spikes`)];

/** Lower scores are better. The strip's title names the period, so each figure names what it is against. */
function againstBaseline(value: number | null, reference: number | null | undefined): string {
  if (reference === undefined || reference === null) return "No baseline";
  const comparison = formatBetter(value, reference);
  return comparison === NO_VALUE ? comparison : `${comparison} than baseline`;
}

/** The diagnostic scores as one strip, the same look as the key figures on the Now screen. Rule 5: the title keeps them labelled as diagnostics. */
function ScoreStrip({ performance, heading }: { performance: Performance; heading: string }) {
  const model = performance.diagnostic.model?.overall;
  const baseline = performance.diagnostic.baseline?.overall;
  if (!model) return null;
  return (
    <StatStrip label={heading} heading={heading}>
      {METRICS.map(({ key, label, short, digits, unit }) => {
        const value = model[key] as number | null;
        const reference = baseline?.[key] as number | null | undefined;
        return (
          <Stat
            key={key}
            label={short}
            hint={label}
            value={unit && value !== null ? <Euro value={value} digits={digits} /> : formatScore(value, digits)}
            detail={againstBaseline(value, reference)}
          />
        );
      })}
      {SPIKES.map(({ side, observed, forecast, hint }) => (
        <Stat
          key={side}
          label={`${side} spikes`}
          hint={hint}
          value={formatPercent(model[observed])}
          detail={`Forecast ${formatPercent(model[forecast])}`}
        />
      ))}
    </StatStrip>
  );
}

function OfficialTable({ performance }: { performance: Performance }) {
  const official = performance.official;
  if (!official) {
    return (
      <p className="px-2 py-2 text-xs text-muted-foreground">
        <FileCheck className="mr-1 inline size-3.5 align-[-2px]" aria-hidden />
        The organiser&apos;s score.py results for the validation period come with real data. Demo data has none.
      </p>
    );
  }
  const rows = [...METRICS, { key: "coverage_p10_p90" as const, label: COVERAGE_LABEL, digits: 3 }];
  return (
    <Table className="text-xs">
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead className="h-auto px-2 py-1.5">Metric</TableHead>
          <TableHead className="h-auto px-2 py-1.5 text-right">Model</TableHead>
          <TableHead className="h-auto px-2 py-1.5 text-right">Baseline</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map(({ key, label, digits }) => (
          <TableRow key={key}>
            <TableCell className="px-2 py-1.5">{label}</TableCell>
            <TableCell className="px-2 py-1.5 text-right font-medium">{formatScore(official.model.overall[key] as number | null, digits)}</TableCell>
            <TableCell className="px-2 py-1.5 text-right">{formatScore(official.baseline?.overall[key] as number | null | undefined, digits)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function HindsightScreen() {
  const { asOf, current, observedUntil } = useViewingTime();
  const wide = useIsWide();
  const across = useDefaultLayout({ id: "hindsight-across", panelIds: ["evidence", "situations"], storage: safeStorage });
  const [range, setRange] = useUrlChoice<Range>("range", ["day", "week", "month"], "week");
  // Nothing observed in the test period is shown, so there the period ends where it starts.
  const end = current && observedUntil && hoursBetween(observedUntil, current) > 0 ? observedUntil : current;
  const from = end ? addHours(end, -RANGES[range].hours) : "";
  const to = end ?? "";
  const ready = current !== undefined;
  const stripHeading = `Diagnostic for ${RANGES[range].title}`;

  const performance = useQuery({ ...queries.performance(asOf, from, to), enabled: ready });
  const hindsight = useQuery({ ...queries.hindsight(asOf, from, to, LEAD_HOURS), enabled: ready });
  const observed = useQuery({ ...queries.actualsBetween(asOf, from, to), enabled: ready });
  const history = useQuery(queries.alertHistory(asOf));
  const situations = useMemo(
    () => (history.data?.situations ?? []).filter((situation) => situation.first_origin_utc >= from && situation.first_origin_utc <= to),
    [history.data, from, to],
  );

  const scores = (
    <QueryState
      query={performance}
      className="h-auto min-h-fit shrink-0"
      isEmpty={(data) => !data.diagnostic.model}
      empty={null}
      skeleton={<StatStripSkeleton labels={STRIP_LABELS} heading={stripHeading} />}
    >
      {(data) => <ScoreStrip performance={data} heading={stripHeading} />}
    </QueryState>
  );

  const chart = (
    <Panel label="Forecast against what happened" className="h-full">
      <PanelHeader title="Forecast vs actual" note={`${PRICE_UNIT}, shaded band (prediction interval 80%)`} oneRow />
      <PanelBody className="pb-2">
        <QueryState
          query={hindsight}
          isEmpty={(data) => !data.points.some((point) => point.actual !== null)}
          empty={
            <PanelMessage icon={CircleDashed} title="Nothing to compare yet">
              Move the viewing time later, or choose a longer period.
            </PanelMessage>
          }
          skeleton={<Skeleton className="h-full w-full" />}
        >
          {(data) => <HindsightChart points={data.points} observed={observed.data?.points ?? NO_ACTUALS} leadHours={data.lead_hours} />}
        </QueryState>
      </PanelBody>
      <div className="flex shrink-0 items-center gap-3 border-t border-hairline-soft px-4 py-2">
        <span className="shrink-0 text-xs text-muted-foreground">Period</span>
        <Choice
          label="Period"
          value={range}
          options={(Object.keys(RANGES) as Range[]).map((value) => ({ value, label: RANGES[value].label }))}
          onChange={setRange}
          fill
        />
      </div>
    </Panel>
  );

  const situationsBox = (
    <Panel label="Situations raised in this period" className="h-full">
      <PanelHeader title="Situations raised" highlight note={`${formatCount(situations.length)} in this period`} />
      <PanelBody className="px-0 pb-0">
        <QueryState
          query={history}
          isEmpty={() => situations.length === 0}
          empty={
            <PanelMessage icon={CheckCheck} title="No situations in this period">
              Choose a longer period, or move the viewing time.
            </PanelMessage>
          }
          skeleton={<SkeletonLines rows={6} className="px-4" />}
        >
          {() => <SituationLog situations={situations} />}
        </QueryState>
      </PanelBody>
      <section aria-label="Official validation scores" className="shrink-0 border-t border-hairline-soft pb-2">
        <PanelHeader title="Official validation scores" highlight />
        <div className="px-2">
          <QueryState query={performance} className="h-auto min-h-fit" skeleton={<SkeletonLines rows={5} className="px-2" />}>
            {(data) => <OfficialTable performance={data} />}
          </QueryState>
        </div>
      </section>
    </Panel>
  );

  return (
    <>
      {/* The sidebar names the screen; the heading stays for screen readers and keeps one h1 per page. */}
      <h1 className="sr-only">Hindsight</h1>
      {wide === null ? (
        <Skeleton className="min-h-0 flex-1" />
      ) : wide ? (
        // Like the Now screen: the evidence on the left, the situations in a full-height box on the right.
        <div className="min-h-[36rem] flex-1">
          <ResizablePanelGroup orientation="horizontal" className="h-full" defaultLayout={across.defaultLayout} onLayoutChanged={across.onLayoutChanged}>
            <ResizablePanel id="evidence" defaultSize="66">
              <div className="flex h-full min-h-0 flex-col gap-3">
                {scores}
                <div className="min-h-0 flex-1">{chart}</div>
              </div>
            </ResizablePanel>
            <ResizableHandle className={GAP_HANDLE} aria-label="Resize the situations panel" />
            <ResizablePanel id="situations" defaultSize="34" minSize="26" maxSize="45">
              {situationsBox}
            </ResizablePanel>
          </ResizablePanelGroup>
        </div>
      ) : (
        <div className="flex shrink-0 flex-col gap-3">
          {scores}
          <div className="h-[40rem]">{chart}</div>
          <div className="h-[36rem]">{situationsBox}</div>
        </div>
      )}
    </>
  );
}
