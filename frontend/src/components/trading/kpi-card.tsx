import type { ReactNode } from "react";

import { Skeleton } from "@/components/ui/skeleton";

/** One headline number: sans label, serif value at 24 px or more, and a line of context. */
export function KpiCard({ label, value, unit, detail }: { label: string; value: ReactNode; unit?: ReactNode; detail?: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1 rounded-lg border bg-card px-4 py-3">
      <p className="eyebrow truncate text-stone">{label}</p>
      <p className="flex min-w-0 items-baseline gap-1.5">
        <span className="font-title truncate text-3xl text-ink">{value}</span>
        {unit}
      </p>
      <p className="truncate text-xs text-muted-foreground">{detail ?? " "}</p>
    </div>
  );
}

export function KpiCardSkeleton({ label }: { label: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border bg-card px-4 py-3">
      <p className="eyebrow truncate text-stone">{label}</p>
      <Skeleton className="my-1 h-8 w-24" />
      <Skeleton className="h-3.5 w-28" />
    </div>
  );
}
