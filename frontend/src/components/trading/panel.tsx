import { CircleAlert, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/** White surface, 1 px hairline, no shadow. Takes keyboard focus through F6 (see use-shortcuts). */
export function Panel({ label, className, children }: { label: string; className?: string; children: ReactNode }) {
  return (
    <section aria-label={label} data-panel tabIndex={-1} className={cn("flex min-h-0 flex-col rounded-lg border bg-card", className)}>
      {children}
    </section>
  );
}

export function PanelHeader({ title, note, children }: { title: string; note?: ReactNode; children?: ReactNode }) {
  return (
    <header className="flex min-h-10 shrink-0 flex-wrap items-center justify-between gap-x-3 gap-y-1 px-4 pt-3 pb-2">
      <div className="flex min-w-0 items-baseline gap-2">
        <h2 className="eyebrow text-stone">{title}</h2>
        {note ? <p className="truncate text-xs text-muted-foreground">{note}</p> : null}
      </div>
      {children ? <div className="flex shrink-0 items-center gap-2">{children}</div> : null}
    </header>
  );
}

export function PanelBody({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("min-h-0 flex-1 px-4 pb-4", className)}>{children}</div>;
}

/** Empty and error states: one line of explanation and, where there is one, the next action. */
export function PanelMessage({
  icon: Icon,
  title,
  children,
  action,
}: {
  icon: LucideIcon;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex h-full min-h-24 flex-col items-center justify-center gap-1.5 px-4 py-6 text-center">
      <Icon className="size-5 shrink-0 text-muted-foreground" aria-hidden />
      <p className="text-base font-medium">{title}</p>
      {children ? <p className="max-w-sm text-sm text-muted-foreground">{children}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export function PanelError({ error, onRetry, onBackToLatest }: { error: unknown; onRetry?: () => void; onBackToLatest?: () => void }) {
  const detail = error instanceof Error ? error.message : "Something went wrong.";
  return (
    <PanelMessage
      icon={CircleAlert}
      title="This could not be loaded"
      action={
        <div className="flex gap-2">
          {onRetry ? (
            <Button variant="outline" size="sm" onClick={onRetry}>
              Try again
            </Button>
          ) : null}
          {onBackToLatest ? (
            <Button variant="ghost" size="sm" onClick={onBackToLatest}>
              Back to latest
            </Button>
          ) : null}
        </div>
      }
    >
      {detail}
    </PanelMessage>
  );
}

export function SkeletonLines({ rows = 3, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-2", className)} aria-hidden>
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} className="h-4 w-full" />
      ))}
    </div>
  );
}
