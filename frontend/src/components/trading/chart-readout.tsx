import type { ReactNode, RefObject } from "react";

import type { DirectionReadout } from "@/lib/chart/direction-pane";
import { cn } from "@/lib/utils";

/** `width` keeps a value's place while the crosshair moves. In em, as the text size follows the band. */
export type ReadoutSpec = { key: string; label: string; swatch?: string; width: string };

/**
 * The band above a chart, naming what the crosshair is on. It has the look of a highlighted panel title,
 * so the names and numbers read first. The owner writes values straight to the DOM by `data-field`, as the
 * crosshair moves too often to re-render React for it. The text follows the band's own width (a container
 * query), as the panel resizes, so the row holds on one line: 11 px with tighter gaps from 38rem (the
 * default split at 1280 px), 12 px from 43rem, 13 px from 47rem, 14 px from 50rem. Each step starts where
 * the row with realistic values was measured to fit. On one line, the items share out any room left over,
 * so the row spans the band evenly. Below 38rem, a phone or a panel dragged narrow, it wraps instead of
 * cutting off its values.
 */
export function Readout({ ref, children }: { ref: RefObject<HTMLDivElement | null>; children: ReactNode }) {
  return (
    <div ref={ref} className="@container shrink-0 rounded-md bg-fill px-2 py-1.5 whitespace-nowrap text-ink">
      {children}
    </div>
  );
}

/** The direction row is painted on a canvas, which cannot be read aloud, so the band holds its words too. */
export function DirectionText() {
  return <span data-field="direction" className="sr-only" />;
}

export function writeDirectionText(root: HTMLElement | null, { up, down, happened }: DirectionReadout): void {
  const target = root?.querySelector("[data-field=direction]");
  if (target) target.textContent = `Balancing direction: up ${up}, down ${down}.${happened ? ` Happened ${happened.text}.` : ""}`;
}

export function ReadoutRow({ fields, showsTime = false }: { fields: readonly ReadoutSpec[]; showsTime?: boolean }) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5 text-xs",
        "@min-[38rem]:flex-nowrap @min-[38rem]:justify-between @min-[38rem]:gap-x-1 @min-[38rem]:text-[0.6875rem]/[1.35]",
        "@min-[43rem]:gap-x-1.5 @min-[43rem]:text-xs @min-[47rem]:gap-x-2 @min-[47rem]:text-sm @min-[50rem]:text-base",
      )}
    >
      {/* The time fills its whole width, so it gets the room the values keep beside them. */}
      {showsTime ? <span data-field="time" className="min-w-[6.2em] pr-[0.5em] font-semibold" /> : null}
      {fields.map((field) => (
        <span key={field.key} className="inline-flex items-baseline gap-1 @min-[38rem]:gap-0.75 @min-[43rem]:gap-1">
          {field.swatch ? <span className={cn("size-2.5 self-center rounded-xs", field.swatch)} aria-hidden /> : null}
          <span className="font-medium">{field.label}</span>
          <span data-field={field.key} className={cn("font-semibold tabular-nums", field.width)} />
        </span>
      ))}
    </div>
  );
}
