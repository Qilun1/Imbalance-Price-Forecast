"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import { Check, Clock, type LucideIcon, Minus, X } from "lucide-react";
import { useRef } from "react";

import type { Situation } from "@/lib/api/client";
import { formatCount, formatDateTime, formatWindowWithDay, hoursBetween } from "@/lib/format";
import { useViewingTime } from "@/lib/realtime/viewing-time";

import { SeverityBadge } from "./situations";

const ITEM_HEIGHT = 64;
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
    <span className={`inline-flex shrink-0 items-center gap-1 text-xs ${tone}`} title={situation.outcome_note ?? undefined}>
      <Icon className="size-3.5 shrink-0" aria-hidden />
      {label}
    </span>
  );
}

const key = (situation: Situation) =>
  `${situation.first_origin_utc}|${situation.alert.kind}|${situation.alert.title}|${situation.alert.window_start_utc}`;

/** Two lines: level, title and outcome; then when it was first raised (opens that moment), its window and updates. */
function Item({ situation, onOpen }: { situation: Situation; onOpen: (time: string) => void }) {
  const { alert, first_origin_utc: first, last_origin_utc: last } = situation;
  const updates = hoursBetween(first, last) + 1;
  return (
    <div className="flex flex-col gap-1 border-b border-hairline-soft px-4 py-2.5">
      <div className="flex items-start gap-2">
        <SeverityBadge severity={alert.severity} />
        <span className="min-w-0 flex-1 text-sm text-ink">{alert.title}</span>
        <Outcome situation={situation} />
      </div>
      <div className="flex flex-wrap items-baseline gap-x-2 text-xs text-muted-foreground">
        <button
          type="button"
          onClick={() => onOpen(first)}
          className="rounded-xs text-ink underline underline-offset-2"
          aria-label={`Go to ${formatDateTime(first)}, when “${alert.title}” was first raised`}
        >
          {formatDateTime(first)}
        </button>
        <span>for {formatWindowWithDay(alert.window_start_utc, alert.window_end_utc)}</span>
        <span>
          {formatCount(updates)} {updates === 1 ? "update" : "updates"}
        </span>
      </div>
    </div>
  );
}

/** Past situations, newest first. Opening one moves the viewing time to when it was first raised. */
export function SituationLog({ situations }: { situations: readonly Situation[] }) {
  const { setTime } = useViewingTime();
  const scroller = useRef<HTMLDivElement>(null);
  const rows = situations.toReversed();
  const virtual = rows.length > VIRTUAL_FROM;
  // eslint-disable-next-line react-hooks/incompatible-library -- virtualising is exactly what a long log needs
  const virtualizer = useVirtualizer({
    count: rows.length,
    enabled: virtual,
    getScrollElement: () => scroller.current,
    estimateSize: () => ITEM_HEIGHT,
    overscan: 8,
  });

  return (
    <div ref={scroller} data-slot="situation-log" className="scrollbar-thin h-full overflow-auto">
      {virtual ? (
        <ul className="relative" style={{ height: virtualizer.getTotalSize() }}>
          {virtualizer.getVirtualItems().map((item) => {
            const situation = rows[item.index];
            if (!situation) return null;
            return (
              <li
                key={key(situation)}
                data-index={item.index}
                ref={virtualizer.measureElement}
                className="absolute top-0 left-0 w-full"
                style={{ transform: `translateY(${item.start}px)` }}
              >
                <Item situation={situation} onOpen={setTime} />
              </li>
            );
          })}
        </ul>
      ) : (
        <ul>
          {rows.map((situation) => (
            <li key={key(situation)}>
              <Item situation={situation} onOpen={setTime} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
