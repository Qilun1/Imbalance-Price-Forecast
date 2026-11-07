"use client";

import { useQuery } from "@tanstack/react-query";
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Clock,
  Pause,
  Play,
  TriangleAlert,
  Undo2,
} from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { queries } from "@/lib/api/queries";
import { formatClockUtc, formatDateTimeUtc, formatMinutes, formatUtc, fromUtcDate, toCalendarDate, utcHour } from "@/lib/format";
import { useViewingTime } from "@/lib/realtime/viewing-time";

import { CompactNav } from "./sidebar";

const HOURS = Array.from({ length: 24 }, (_, hour) => hour);

function Hint({ text, children }: { text: string; children: ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent>{text}</TooltipContent>
    </Tooltip>
  );
}

function Step({ hours, label, children }: { hours: number; label: string; children: ReactNode }) {
  const { step, canStep } = useViewingTime();
  return (
    <Hint text={label}>
      <span>
        <Button variant="ghost" size="icon-sm" aria-label={label} disabled={!canStep(hours)} onClick={() => step(hours)}>
          {children}
        </Button>
      </span>
    </Hint>
  );
}

function TimePicker() {
  const { current, first, last, setTime } = useViewingTime();
  if (!current || !first || !last) return <Skeleton className="h-7 w-48 rounded-full" />;
  const day = toCalendarDate(current);
  const hour = utcHour(current);
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" aria-label={`Viewing time ${formatDateTimeUtc(current)}. Change it`}>
          <CalendarDays data-icon="inline-start" aria-hidden />
          {formatDateTimeUtc(current)}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-auto">
        <Calendar
          mode="single"
          selected={day}
          defaultMonth={day}
          disabled={{ before: toCalendarDate(first), after: toCalendarDate(last) }}
          onSelect={(date) => {
            if (date) setTime(fromUtcDate(date, hour));
          }}
        />
        <div className="flex items-center justify-between gap-3 px-1 pt-2">
          <span id="viewing-hour" className="text-sm text-stone">
            Hour, UTC
          </span>
          <Select value={String(hour)} onValueChange={(value) => setTime(fromUtcDate(day, Number(value)))}>
            <SelectTrigger aria-labelledby="viewing-hour" className="w-24">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {HOURS.map((value) => (
                <SelectItem key={value} value={String(value)}>
                  {String(value).padStart(2, "0")}:00
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function ReplayButton() {
  const { isPast, replaying, toggleReplay, canStep } = useViewingTime();
  if (!isPast) return null;
  const label = replaying ? "Pause the replay" : "Replay hour by hour";
  const Icon = replaying ? Pause : Play;
  return (
    <Hint text={`${label} (R)`}>
      <span>
        <Button variant="ghost" size="icon-sm" aria-label={label} aria-pressed={replaying} disabled={!canStep(1)} onClick={toggleReplay}>
          <Icon aria-hidden />
        </Button>
      </span>
    </Hint>
  );
}

export function ViewingTimeControl() {
  const { isPast, toLatest } = useViewingTime();
  return (
    <div role="group" aria-label="Viewing time" className="flex items-center gap-0.5">
      <Step hours={-24} label="One day back">
        <ChevronsLeft aria-hidden />
      </Step>
      <Step hours={-1} label="One hour back">
        <ChevronLeft aria-hidden />
      </Step>
      <TimePicker />
      <Step hours={1} label="One hour forward">
        <ChevronRight aria-hidden />
      </Step>
      <Step hours={24} label="One day forward">
        <ChevronsRight aria-hidden />
      </Step>
      <ReplayButton />
      {isPast ? (
        <Button variant="secondary" size="sm" className="ml-1" onClick={toLatest}>
          <Undo2 data-icon="inline-start" aria-hidden />
          Back to latest
        </Button>
      ) : null}
    </div>
  );
}

function Stamp() {
  const { asOf } = useViewingTime();
  const { data: forecast } = useQuery(queries.forecast(asOf));
  const { data: alerts } = useQuery(queries.alerts(asOf));
  if (!forecast) return <Skeleton className="h-4 w-64" />;
  const stale = alerts?.alerts.some((alert) => alert.kind === "stale_data") ?? false;
  const Icon = stale ? TriangleAlert : Clock;
  const cutoff = forecast.data_cutoff_utc;
  return (
    <Hint
      text={`Forecast made ${formatUtc(forecast.origin_utc)}. Latest data ${cutoff ? formatUtc(cutoff) : "unknown"}. Spot known until ${
        forecast.spot_known_until_utc ? formatUtc(forecast.spot_known_until_utc) : "unknown"
      }.`}
    >
      <p tabIndex={0} className={`flex min-w-0 items-center gap-1.5 truncate rounded-xs text-xs ${stale ? "text-warning" : "text-stone"}`}>
        <Icon className="size-4 shrink-0" aria-hidden />
        <span className="truncate">
          Forecast made {formatClockUtc(forecast.origin_utc)}
          {cutoff ? `, latest data ${formatClockUtc(cutoff)} (${formatMinutes(forecast.data_age_minutes)} old)` : ", data time unknown"}
        </span>
      </p>
    </Hint>
  );
}

export function TopBar({ onCommand }: { onCommand: () => void }) {
  return (
    <header className="flex min-h-topbar shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-b bg-canvas px-3 py-2">
      <CompactNav />
      <ViewingTimeControl />
      <div className="hidden min-w-0 flex-1 lg:block">
        <Stamp />
      </div>
      <Button variant="outline" size="sm" className="ml-auto hidden md:inline-flex" onClick={onCommand} aria-label="Ctrl K, command menu">
        Ctrl K
      </Button>
      <div className="w-full min-w-0 lg:hidden">
        <Stamp />
      </div>
    </header>
  );
}
