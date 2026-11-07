import type { ReactNode, RefObject } from "react";

import { cn } from "@/lib/utils";

/** `width` keeps a value's place while the crosshair moves, so the band never rewraps and resizes the chart. */
export type ReadoutSpec = { key: string; label: string; swatch?: string; width: string };

/**
 * The band above a chart, naming what the crosshair is on. It has the look of a highlighted panel title,
 * so the names and numbers read first. The owner writes values straight to the DOM by `data-field`, as the
 * crosshair moves too often to re-render React for it.
 */
export function Readout({ ref, children }: { ref: RefObject<HTMLDivElement | null>; children: ReactNode }) {
  return (
    <div ref={ref} className="flex shrink-0 flex-col gap-0.5 rounded-md bg-fill px-2 py-1.5 text-base whitespace-nowrap text-ink">
      {children}
    </div>
  );
}

export function ReadoutRow({ fields, showsTime = false, children }: { fields: readonly ReadoutSpec[]; showsTime?: boolean; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
      {showsTime ? <span data-field="time" className="min-w-22 font-semibold" /> : null}
      {fields.map((field) => (
        <span key={field.key} className="inline-flex items-baseline gap-1">
          {field.swatch ? <span className={cn("size-2.5 self-center rounded-xs", field.swatch)} aria-hidden /> : null}
          <span className="font-medium">{field.label}</span>
          <span data-field={field.key} className={cn("font-semibold tabular-nums", field.width)} />
        </span>
      ))}
      {children}
    </div>
  );
}
