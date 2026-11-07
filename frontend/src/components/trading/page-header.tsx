import type { ReactNode } from "react";

export function PageHeader({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex shrink-0 flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
      <h1 className="font-title text-3xl text-ink">{title}</h1>
      {children}
    </div>
  );
}
