"use client";

import { useQueries } from "@tanstack/react-query";
import { ClipboardCopy, History } from "lucide-react";
import dynamic from "next/dynamic";
import { useCallback } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import type { Alert, Forecast } from "@/lib/api/client";
import { queries } from "@/lib/api/queries";
import {
  addHours,
  formatCount,
  formatDate,
  formatDateTimeUtc,
  formatMinutes,
  formatPercent,
  formatPoints,
  formatPriceWithUnit,
  formatSignedPrice,
  formatWindow,
  hoursBetween,
  PRICE_UNIT,
} from "@/lib/format";
import { evidenceItems, revisionTrail, windowOf } from "@/lib/forecast";
import { useViewingTime } from "@/lib/realtime/viewing-time";

import { useNow } from "./now-context";
import { PanelMessage } from "./panel";
import { KIND_LABELS, SeverityBadge } from "./situations";

const RevisionChart = dynamic(() => import("./revision-chart"), { ssr: false, loading: () => <Skeleton className="h-56 w-full" /> });

/** The forecast covers 10 hours, so a window can have been seen by at most the last 10 updates. */
const UPDATES = 10;

function evidenceText(kind: ReturnType<typeof evidenceItems>[number]["kind"], key: string, value: number): string {
  switch (kind) {
    case "probability":
      return formatPercent(value);
    case "points":
      return formatPoints(value);
    case "minutes":
      return formatMinutes(value);
    case "count":
      return formatCount(value);
    case "price":
      return key === "largest_p50_change" ? `${formatSignedPrice(value)} ${PRICE_UNIT}` : formatPriceWithUnit(value);
  }
}

function useEarlierForecasts(): { forecasts: Forecast[]; pending: boolean } {
  const { current, first } = useViewingTime();
  const origins = !current || !first
    ? []
    : Array.from({ length: UPDATES }, (_, index) => addHours(current, -index)).filter((origin) => hoursBetween(first, origin) >= 0);
  return useQueries({
    queries: origins.map((origin) => queries.forecast(origin)),
    combine: useCallback(
      (results: { data?: Forecast; isPending: boolean }[]) => ({
        forecasts: results.flatMap((result) => (result.data ? [result.data] : [])),
        pending: results.some((result) => result.isPending),
      }),
      [],
    ),
  });
}

function RevisionTrail({ alert }: { alert: Alert }) {
  const { forecasts, pending } = useEarlierForecasts();
  if (pending) return <Skeleton className="h-56 w-full" />;
  const points = revisionTrail(forecasts, windowOf(alert));
  if (points.length < 2) {
    return (
      <PanelMessage icon={History} title="This is the first forecast of this window">
        Its development shows from the next update on.
      </PanelMessage>
    );
  }
  return <RevisionChart points={points} />;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-1.5">
      <h3 className="eyebrow text-stone">{title}</h3>
      {children}
    </section>
  );
}

function shiftNote(alert: Alert, madeAt: string): string {
  return `Forecast ${formatDateTimeUtc(madeAt)}. ${alert.title}, ${formatDate(alert.window_start_utc)} ${formatWindow(alert.window_start_utc, alert.window_end_utc)} UTC. ${alert.message}`;
}

function Review({ alert }: { alert: Alert }) {
  const { current } = useViewingTime();
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(shiftNote(alert, current ?? alert.window_start_utc));
      toast.success("Copied as a shift note");
    } catch {
      toast.error("Copying is blocked in this browser");
    }
  };
  const evidence = evidenceItems(alert.evidence);
  return (
    <>
      <SheetHeader className="gap-1 border-b p-4 pr-12">
        <div className="flex items-center gap-2">
          <SeverityBadge severity={alert.severity} />
          <span className="text-xs text-muted-foreground">{KIND_LABELS[alert.kind]}</span>
        </div>
        <SheetTitle className="text-lg font-medium">{alert.title}</SheetTitle>
        <SheetDescription>
          {formatDate(alert.window_start_utc)}, {formatWindow(alert.window_start_utc, alert.window_end_utc)} UTC
        </SheetDescription>
      </SheetHeader>
      <ScrollArea className="min-h-0 flex-1">
        <div className="flex flex-col gap-4 p-4">
          <Section title="Reasoning">
            <p className="text-base text-ink">{alert.message}</p>
          </Section>
          <div className="rounded-md bg-fill p-3">
            <p className="eyebrow text-stone">Worth checking</p>
            <p className="mt-1 text-base text-ink first-letter:uppercase">{alert.check}</p>
          </div>
          {evidence.length ? (
            <Section title="Evidence">
              <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm">
                {evidence.map((item) => (
                  <div key={item.key} className="contents">
                    <dt className="text-muted-foreground">{item.label}</dt>
                    <dd className="text-right text-ink">{evidenceText(item.kind, item.key, item.value)}</dd>
                  </div>
                ))}
              </dl>
            </Section>
          ) : null}
          {alert.drivers.length ? (
            <Section title="Main factors">
              <ul className="list-inside list-disc text-sm text-ink">
                {alert.drivers.map((driver) => (
                  <li key={driver.id}>{driver.label}</li>
                ))}
              </ul>
            </Section>
          ) : null}
          <Section title="How it developed">
            <RevisionTrail alert={alert} />
          </Section>
          <p className="text-xs text-muted-foreground">
            A suggestion to review, not an instruction. Open data does not show free capacity, marginal cost, ramp speed, or whether capacity is
            already committed.
          </p>
        </div>
      </ScrollArea>
      <SheetFooter className="border-t p-4">
        <Button variant="outline" onClick={copy}>
          <ClipboardCopy data-icon="inline-start" aria-hidden />
          Copy as a shift note
        </Button>
      </SheetFooter>
    </>
  );
}

export function SituationSheet() {
  const { reviewing, review } = useNow();
  return (
    <Sheet
      open={reviewing !== null}
      onOpenChange={(open) => {
        if (!open) review(null);
      }}
    >
      <SheetContent className="flex w-full flex-col gap-0 sm:max-w-md data-[side=right]:sm:max-w-md">
        {reviewing ? <Review alert={reviewing} /> : <SheetTitle className="sr-only">Review situation</SheetTitle>}
      </SheetContent>
    </Sheet>
  );
}
