"use client";

import { useQuery } from "@tanstack/react-query";
import { type PointerEvent, useMemo, useRef } from "react";

import type { SituationHour } from "@/lib/api/client";
import { queries } from "@/lib/api/queries";
import { addHours, formatDateTimeUtc, hoursBetween } from "@/lib/format";
import { useViewingTime } from "@/lib/realtime/viewing-time";

type Block = { start: number; hours: number; review: boolean };

/** Neighbouring hours of the same level become one block, so the strip has no hairline gaps. */
function toBlocks(hours: readonly SituationHour[], first: string): Block[] {
  const blocks: Block[] = [];
  for (const hour of hours) {
    const start = hoursBetween(first, hour.origin_utc);
    const review = hour.review > 0;
    const last = blocks.at(-1);
    if (last && last.review === review && last.start + last.hours === start) last.hours += 1;
    else blocks.push({ start, hours: 1, review });
  }
  return blocks;
}

/**
 * The whole period at a glance: one mark per hour, tall for situations worth a review, short for ones
 * to watch. Click or drag to move the viewing time. Asked of the newest data on purpose, so it can
 * always lead forward as well as back.
 */
export function SituationTimeline() {
  const { current, first, last, setTime, step, canStep } = useViewingTime();
  const { data } = useQuery(queries.alertHistory());
  const track = useRef<HTMLDivElement>(null);
  const label = useRef<HTMLSpanElement>(null);
  const blocks = useMemo(() => (data && first ? toBlocks(data.hours, first) : []), [data, first]);

  if (!first || !last || !current) return <div className="h-timeline shrink-0 border-b bg-canvas" />;
  const hours = Math.max(1, hoursBetween(first, last));
  const position = (hoursBetween(first, current) / hours) * 100;

  const hourAt = (event: PointerEvent<HTMLDivElement>) => {
    const box = track.current?.getBoundingClientRect();
    if (!box) return first;
    const share = Math.min(1, Math.max(0, (event.clientX - box.left) / box.width));
    return addHours(first, Math.round(share * hours));
  };

  const hint = (event: PointerEvent<HTMLDivElement>) => {
    const box = track.current?.getBoundingClientRect();
    if (!box || !label.current) return;
    const left = Math.min(box.width - 144, Math.max(0, event.clientX - box.left - 72));
    label.current.textContent = formatDateTimeUtc(hourAt(event));
    label.current.style.transform = `translateX(${left}px)`;
    label.current.hidden = false;
  };

  return (
    <div className="relative h-timeline shrink-0 border-b bg-canvas px-3">
      <div
        ref={track}
        role="slider"
        tabIndex={0}
        aria-label="Viewing time across the whole period"
        aria-valuemin={0}
        aria-valuemax={hours}
        aria-valuenow={Math.round(hoursBetween(first, current))}
        aria-valuetext={formatDateTimeUtc(current)}
        className="relative h-full cursor-pointer touch-none rounded-xs"
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          setTime(hourAt(event));
        }}
        onPointerMove={(event) => {
          hint(event);
          if (event.buttons === 1) setTime(hourAt(event));
        }}
        onPointerLeave={() => {
          if (label.current) label.current.hidden = true;
        }}
        onKeyDown={(event) => {
          const direction = event.key === "ArrowLeft" ? -1 : event.key === "ArrowRight" ? 1 : 0;
          if (!direction) return;
          event.preventDefault();
          event.stopPropagation();
          const size = event.shiftKey ? 24 : 1;
          if (canStep(direction * size)) step(direction * size);
        }}
      >
        <svg className="absolute inset-0 size-full" viewBox={`0 0 ${hours + 1} 10`} preserveAspectRatio="none" aria-hidden>
          <rect x="0" y="9.6" width={hours + 1} height="0.4" className="fill-hairline" />
          {blocks.map(({ start, hours: width, review }) =>
            review ? (
              <rect key={start} x={start} y="1.5" width={width} height="8.5" className="fill-warning" />
            ) : (
              <rect key={start} x={start} y="6" width={width} height="4" className="fill-silver" />
            ),
          )}
        </svg>
        <span className="absolute inset-y-0 w-0.5 -translate-x-1/2 bg-stone" style={{ left: `${position}%` }} aria-hidden />
        <span
          ref={label}
          hidden
          className="pointer-events-none absolute top-0 left-0 z-10 w-36 rounded-xs bg-ink px-1.5 py-0.5 text-center text-xs text-canvas"
          aria-hidden
        />
      </div>
    </div>
  );
}
