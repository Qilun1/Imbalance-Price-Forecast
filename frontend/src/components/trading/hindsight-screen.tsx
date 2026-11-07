"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCheck, CircleDashed, FileCheck } from "lucide-react";
import dynamic from "next/dynamic";
import { useSearchParams } from "next/navigation";
import { useMemo } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { Performance, Scores, Situation } from "@/lib/api/client";
import { queries } from "@/lib/api/queries";
import { addHours, formatBetter, formatCount, formatPercent, formatScore, PRICE_UNIT } from "@/lib/format";
import { useViewingTime } from "@/lib/realtime/viewing-time";

import { Unit } from "./cells";
import { HorizonChart } from "./horizon-chart";
import { KpiCard, KpiCardSkeleton } from "./kpi-card";
import { PageHeader } from "./page-header";
import { Panel, PanelBody, PanelHeader, PanelMessage, SkeletonLines } from "./panel";
import { QueryState } from "./query-state";
import { SituationLog } from "./situation-log";

const HindsightChart = dynamic(() => import("./hindsight-chart"), {
  ssr: false,
  loading: () => <Skeleton className="h-full min-h-48 w-full" />,
});

const RANGES = {
  day: { label: "Previous day", hours: 24 },
  week: { label: "Previous week", hours: 24 * 7 },
  month: { label: "Previous month", hours: 24 * 30 },
} as const;
type Range = keyof typeof RANGES;

const LEADS = ["1", "4", "10"] as const;

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

function Choice<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: readonly { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <ToggleGroup
      type="single"
      size="sm"
      spacing={1}
      value={value}
      aria-label={label}
      onValueChange={(next) => {
        if (next) onChange(next as T);
      }}
    >
      {options.map((option) => (
        <ToggleGroupItem key={option.value} value={option.value} className="px-3">
          {option.label}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}

const METRICS: readonly { key: keyof Scores; label: string; digits: number; unit?: boolean }[] = [
  { key: "mae_p50", label: "Price error (MAE)", digits: 2, unit: true },
  { key: "calibration_pinball_mean", label: "Uncertainty (pinball)", digits: 2, unit: true },
  { key: "brier_spike_mean", label: "Exceptional prices (Brier)", digits: 3 },
  { key: "brier_direction", label: "Direction (Brier)", digits: 3 },
];

const COVERAGE_TARGET = 0.8;

function ScoreRow({ performance }: { performance: Performance }) {
  const model = performance.diagnostic.model?.overall;
  const baseline = performance.diagnostic.baseline?.overall;
  if (!model) return null;
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
      {METRICS.map(({ key, label, digits, unit }) => {
        const value = model[key] as number | null;
        const reference = baseline?.[key] as number | null | undefined;
        return (
          <KpiCard
            key={key}
            label={label}
            value={formatScore(value, digits)}
            unit={unit ? <Unit /> : undefined}
            detail={reference === undefined || reference === null ? "No baseline for this window" : `${formatBetter(value, reference)} than the baseline`}
          />
        );
      })}
      <KpiCard label="P10–P90 coverage" value={formatPercent(model.coverage_p10_p90)} detail={`Target about ${formatPercent(COVERAGE_TARGET)}`} />
    </div>
  );
}

function OfficialTable({ performance }: { performance: Performance }) {
  const official = performance.official;
  if (!official) {
    return (
      <PanelMessage icon={FileCheck} title="Official scores come with real data">
        These are the organiser&apos;s score.py results for the validation period. Demo data has none.
      </PanelMessage>
    );
  }
  const rows = [
    ...METRICS,
    { key: "coverage_p10_p90" as const, label: "P10–P90 coverage", digits: 3 },
  ];
  return (
    <Table containerClassName="max-w-xl">
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead>Metric</TableHead>
          <TableHead className="text-right">Model</TableHead>
          <TableHead className="text-right">Baseline</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map(({ key, label, digits }) => (
          <TableRow key={key}>
            <TableCell>{label}</TableCell>
            <TableCell className="text-right font-medium">{formatScore(official.model.overall[key] as number | null, digits)}</TableCell>
            <TableCell className="text-right">{formatScore(official.baseline?.overall[key] as number | null | undefined, digits)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

/** A diagnostic in words. Open situations and those that claim nothing are left out of the count. */
function trackRecord(situations: readonly Situation[]): string {
  const judged = situations.filter((situation) => situation.outcome === "happened" || situation.outcome === "did_not_happen");
  const happened = judged.filter((situation) => situation.outcome === "happened").length;
  const count = `${formatCount(situations.length)} in this period`;
  return judged.length ? `${count}. Of ${formatCount(judged.length)} that can be judged, ${formatCount(happened)} happened.` : `${count}.`;
}

export function HindsightScreen() {
  const { asOf, current } = useViewingTime();
  const [range, setRange] = useUrlChoice<Range>("range", ["day", "week", "month"], "week");
  const [lead, setLead] = useUrlChoice("lead", LEADS, "1");
  const from = current ? addHours(current, -RANGES[range].hours) : "";
  const to = current ?? "";
  const ready = current !== undefined;

  const performance = useQuery({ ...queries.performance(asOf, from, to), enabled: ready });
  const hindsight = useQuery({ ...queries.hindsight(asOf, from, to, Number(lead)), enabled: ready });
  const history = useQuery(queries.alertHistory(asOf));
  const situations = useMemo(
    () => (history.data?.situations ?? []).filter((situation) => situation.first_origin_utc >= from),
    [history.data, from],
  );

  return (
    <>
      <PageHeader title="Hindsight">
        <Choice
          label="Period"
          value={range}
          options={(Object.keys(RANGES) as Range[]).map((value) => ({ value, label: RANGES[value].label }))}
          onChange={setRange}
        />
      </PageHeader>

      <QueryState
        query={performance}
        className="h-auto min-h-fit shrink-0"
        isEmpty={(data) => !data.diagnostic.model}
        empty={null}
        skeleton={
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5" aria-hidden>
            {[...METRICS.map((metric) => metric.label), "P10–P90 coverage"].map((label) => (
              <KpiCardSkeleton key={label} label={label} />
            ))}
          </div>
        }
      >
        {(data) => (
          <>
            <ScoreRow performance={data} />
            <p className="mt-1.5 text-xs text-muted-foreground">{data.diagnostic.note}</p>
          </>
        )}
      </QueryState>

      <div className="grid shrink-0 gap-3 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Panel label="Forecast against what happened" className="h-80">
          <PanelHeader title="Forecast vs actual" note={`Diagnostic, in ${PRICE_UNIT}, times in UTC`}>
            <Choice
              label="How far ahead the forecast was made"
              value={lead}
              options={LEADS.map((value) => ({ value, label: `${value} h ahead` }))}
              onChange={setLead}
            />
          </PanelHeader>
          <PanelBody>
            <QueryState
              query={hindsight}
              isEmpty={(data) => data.points.length === 0}
              empty={
                <PanelMessage icon={CircleDashed} title="Nothing to compare yet">
                  Move the viewing time later, or choose a longer period.
                </PanelMessage>
              }
              skeleton={<Skeleton className="h-full w-full" />}
            >
              {(data) => <HindsightChart points={data.points} leadHours={data.lead_hours} />}
            </QueryState>
          </PanelBody>
        </Panel>
        <Panel label="Error by hours ahead" className="h-80">
          <PanelHeader title="Error by hours ahead" note={`Diagnostic, MAE in ${PRICE_UNIT}`} />
          <PanelBody>
            <QueryState
              query={performance}
              isEmpty={(data) => !data.diagnostic.model}
              empty={
                <PanelMessage icon={CircleDashed} title="Nothing to score yet">
                  This period has no realised prices at the viewing time.
                </PanelMessage>
              }
              skeleton={<Skeleton className="h-full w-full" />}
            >
              {(data) => (data.diagnostic.model ? <HorizonChart model={data.diagnostic.model} baseline={data.diagnostic.baseline} /> : null)}
            </QueryState>
          </PanelBody>
        </Panel>
      </div>

      <div className="grid shrink-0 gap-3 3xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Panel label="Situations raised in this period" className="h-72">
          <PanelHeader title="Situations raised" note={trackRecord(situations)} />
          <PanelBody className="px-1 pb-1">
            <QueryState
              query={history}
              isEmpty={() => situations.length === 0}
              empty={
                <PanelMessage icon={CheckCheck} title="No situations in this period">
                  Choose a longer period, or move the viewing time.
                </PanelMessage>
              }
              skeleton={<SkeletonLines rows={6} className="px-3" />}
            >
              {() => <SituationLog situations={situations} />}
            </QueryState>
          </PanelBody>
        </Panel>
        <Panel label="Official validation scores" className="h-72">
          <PanelHeader title="Official validation scores" note="score.py, 7 Sep to 4 Oct" />
          <PanelBody className="scrollbar-thin overflow-auto px-1">
            <QueryState query={performance} skeleton={<SkeletonLines rows={5} className="px-3" />}>
              {(data) => <OfficialTable performance={data} />}
            </QueryState>
          </PanelBody>
        </Panel>
      </div>
    </>
  );
}
