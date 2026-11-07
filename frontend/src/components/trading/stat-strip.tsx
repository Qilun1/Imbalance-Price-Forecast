import type { ReactNode } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { formatEuro } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Columns follow the strip's own width (a container query), since it shares the row with a side box.
 * Wide enough, the figures share one row equally, however many there are.
 */
const STRIP = "@container shrink-0 rounded-lg border border-hairline-soft bg-card px-4 py-2.5";
const GRID = "grid grid-cols-2 gap-x-4 gap-y-2.5 @lg:grid-cols-3 @xl:grid-cols-none @xl:grid-flow-col @xl:auto-cols-fr";
const HEADING = "eyebrow pb-2 text-stone";

/**
 * One figure in the strip: quiet label, plain large number, short context. Styled after a market quote line.
 * With `onSelect` the whole figure is a toggle button, laid over it so the text keeps its own elements.
 */
export function Stat({
  label,
  value,
  detail,
  tone,
  hint,
  onSelect,
  selected = false,
  action,
}: {
  label: string;
  value: ReactNode;
  detail: ReactNode;
  tone?: string;
  /** Hover text for the label, such as the full name of a score. */
  hint?: string;
  onSelect?: () => void;
  selected?: boolean;
  /** The button's name, saying what pressing it does. */
  action?: string;
}) {
  return (
    <div
      className={cn(
        "relative flex min-w-0 flex-col gap-0.5",
        onSelect && "-mx-2 -my-1 rounded-md px-2 py-1 transition-colors hover:bg-fill/60",
        selected && "bg-fill hover:bg-fill",
      )}
    >
      <p className="truncate text-xs text-muted-foreground" title={hint ?? label}>
        {label}
      </p>
      {/* div, not p: while loading these hold a Skeleton, which is a div and may not sit inside a p. */}
      <div className={cn("flex min-w-0 items-baseline truncate text-xl font-semibold text-ink", tone)}>{value}</div>
      <div className="truncate text-xs text-muted-foreground" title={typeof detail === "string" ? detail : undefined}>
        {detail}
      </div>
      {onSelect ? (
        <button
          type="button"
          aria-pressed={selected}
          aria-label={action ?? label}
          title={action}
          onClick={onSelect}
          className="absolute inset-0 cursor-pointer rounded-md"
        />
      ) : null}
    </div>
  );
}

/** A row of figures in one quiet box. `heading` adds a visible title where the figures need naming. */
export function StatStrip({ label, heading, children }: { label: string; heading?: string; children: ReactNode }) {
  return (
    <section aria-label={label} className={STRIP}>
      {heading ? <h2 className={HEADING}>{heading}</h2> : null}
      <div className={GRID}>{children}</div>
    </section>
  );
}

/**
 * The strip's loading state, keeping each label and the heading so the layout does not jump. `tallDetail`
 * is for a strip with a two-line detail.
 */
export function StatStripSkeleton({ labels, heading, tallDetail = false }: { labels: readonly string[]; heading?: string; tallDetail?: boolean }) {
  return (
    <div className={STRIP} aria-hidden>
      {heading ? <p className={HEADING}>{heading}</p> : null}
      <div className={GRID}>
        {labels.map((label) => (
          <Stat key={label} label={label} value={<Skeleton className="my-1 h-5 w-20" />} detail={<Skeleton className={tallDetail ? "h-8 w-24" : "h-3 w-24"} />} />
        ))}
      </div>
    </div>
  );
}

/** Dropped when the strip is narrow, so the figures still fit in one row; the chart note names the unit. */
const PerMwh = () => <span className="ml-1 hidden text-xs font-normal text-muted-foreground @2xl:inline">/MWh</span>;

export function Euro({ value, plus = false, digits = 1 }: { value: number; plus?: boolean; digits?: number }) {
  return (
    <>
      {formatEuro(value, { plus, digits })}
      <PerMwh />
    </>
  );
}
