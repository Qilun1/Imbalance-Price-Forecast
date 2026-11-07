"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import { Check, Clock, type LucideIcon, Minus, X } from "lucide-react";
import { useRef } from "react";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { Situation } from "@/lib/api/client";
import { formatCount, formatDateTime, formatWindowWithDay, hoursBetween } from "@/lib/format";
import { useViewingTime } from "@/lib/realtime/viewing-time";

import { SeverityBadge } from "./situations";

const ROW_HEIGHT = 32;
const VIRTUAL_FROM = 100;

const OUTCOMES: Record<Situation["outcome"], { label: string; icon: LucideIcon; tone: string }> = {
  happened: { label: "Happened", icon: Check, tone: "text-ink" },
  did_not_happen: { label: "Did not happen", icon: X, tone: "text-stone" },
  pending: { label: "Not known yet", icon: Clock, tone: "text-muted-foreground" },
  not_applicable: { label: "No claim to judge", icon: Minus, tone: "text-muted-foreground" },
};

function Outcome({ situation }: { situation: Situation }) {
  const { label, icon: Icon, tone } = OUTCOMES[situation.outcome];
  return (
    <span className={`inline-flex items-center gap-1 ${tone}`} title={situation.outcome_note ?? undefined}>
      <Icon className="size-4 shrink-0" aria-hidden />
      {label}
    </span>
  );
}

function Row({ situation, onOpen }: { situation: Situation; onOpen: (time: string) => void }) {
  const { alert, first_origin_utc: first, last_origin_utc: last } = situation;
  const updates = hoursBetween(first, last) + 1;
  return (
    <TableRow>
      <TableCell>
        <button type="button" onClick={() => onOpen(first)} className="rounded-xs text-ink underline underline-offset-2">
          {formatDateTime(first)}
        </button>
      </TableCell>
      <TableCell>
        <SeverityBadge severity={alert.severity} />
      </TableCell>
      <TableCell>{alert.title}</TableCell>
      <TableCell>{formatWindowWithDay(alert.window_start_utc, alert.window_end_utc)}</TableCell>
      <TableCell className="text-right">{formatCount(updates)}</TableCell>
      <TableCell>
        <Outcome situation={situation} />
      </TableCell>
    </TableRow>
  );
}

/** Past situations, newest first. Opening one moves the viewing time to when it was first raised. */
export function SituationLog({ situations }: { situations: readonly Situation[] }) {
  const { setTime } = useViewingTime();
  const scroller = useRef<HTMLDivElement>(null);
  const rows = situations.toReversed();
  const virtual = rows.length > VIRTUAL_FROM;
  // eslint-disable-next-line react-hooks/incompatible-library -- virtualising is exactly what this table needs
  const virtualizer = useVirtualizer({
    count: rows.length,
    enabled: virtual,
    getScrollElement: () => scroller.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 8,
  });
  const items = virtualizer.getVirtualItems();
  const top = virtual ? (items[0]?.start ?? 0) : 0;
  const bottom = virtual ? virtualizer.getTotalSize() - (items.at(-1)?.end ?? 0) : 0;
  const visible = virtual ? items.flatMap((item) => rows[item.index] ?? []) : rows;

  return (
    <Table containerClassName="scrollbar-thin h-full overflow-auto" containerRef={scroller}>
      <TableHeader className="sticky top-0 z-10 bg-card">
        <TableRow className="hover:bg-transparent">
          <TableHead className="w-36">First raised</TableHead>
          <TableHead className="w-24">Level</TableHead>
          <TableHead className="min-w-72">Situation</TableHead>
          <TableHead className="w-44">Window</TableHead>
          <TableHead className="w-20 text-right">Updates</TableHead>
          <TableHead className="w-40">What happened</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {top > 0 ? (
          <tr aria-hidden>
            <td colSpan={6} style={{ height: top }} />
          </tr>
        ) : null}
        {visible.map((situation) => (
          <Row key={`${situation.first_origin_utc}|${situation.alert.kind}|${situation.alert.title}|${situation.alert.window_start_utc}`} situation={situation} onOpen={setTime} />
        ))}
        {bottom > 0 ? (
          <tr aria-hidden>
            <td colSpan={6} style={{ height: bottom }} />
          </tr>
        ) : null}
      </TableBody>
    </Table>
  );
}
