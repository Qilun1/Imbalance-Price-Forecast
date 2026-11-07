"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { useViewingTime } from "@/lib/realtime/viewing-time";
import { cn } from "@/lib/utils";

import { PanelError } from "./panel";

/**
 * The loading, error and empty states every data panel shares. While a new viewing time loads, the
 * previous answer stays on screen, slightly faded, so nothing jumps.
 */
export function QueryState<T>({
  query,
  skeleton,
  empty,
  isEmpty,
  className,
  children,
}: {
  query: UseQueryResult<T>;
  skeleton: ReactNode;
  empty?: ReactNode;
  isEmpty?: (data: T) => boolean;
  className?: string;
  children: (data: T) => ReactNode;
}) {
  const { isPast, toLatest } = useViewingTime();
  if (query.data === undefined) {
    if (query.isError) return <PanelError error={query.error} onRetry={() => void query.refetch()} onBackToLatest={isPast ? toLatest : undefined} />;
    return <>{skeleton}</>;
  }
  if (isEmpty?.(query.data)) return <>{empty}</>;
  return (
    <div className={cn("h-full min-h-0 transition-opacity duration-150 ease-out", query.isPlaceholderData && "opacity-60", className)}>
      {children(query.data)}
    </div>
  );
}
