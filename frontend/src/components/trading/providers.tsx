"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MotionConfig } from "motion/react";
import { type ReactNode, Suspense, useState } from "react";

import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { shouldRetry } from "@/lib/api/queries";
import { ViewingTimeProvider } from "@/lib/realtime/viewing-time";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: shouldRetry, refetchOnWindowFocus: false, networkMode: "always" } } }),
  );
  return (
    <QueryClientProvider client={client}>
      <TooltipProvider delayDuration={300}>
        <MotionConfig reducedMotion="user">
          <Suspense>
            <ViewingTimeProvider>{children}</ViewingTimeProvider>
          </Suspense>
        </MotionConfig>
        <Toaster position="bottom-right" />
      </TooltipProvider>
    </QueryClientProvider>
  );
}
