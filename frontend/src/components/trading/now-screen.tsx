"use client";

import { useDefaultLayout } from "react-resizable-panels";

import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { Skeleton } from "@/components/ui/skeleton";
import { safeStorage, useIsWide } from "@/lib/browser";

import { NowProvider } from "./now-context";
import { ForecastPanel, KpiRow } from "./now-panels";
import { SituationSheet } from "./situation-sheet";
import { SituationsPanel } from "./situations";

const GAP_HANDLE = "w-3 bg-transparent aria-[orientation=horizontal]:h-3 aria-[orientation=horizontal]:w-full";

function WideLayout() {
  // A new storage id, so sizes saved while the situations were on the left do not apply.
  const across = useDefaultLayout({ id: "now-across-chart-left", panelIds: ["evidence", "situations"], storage: safeStorage });
  return (
    <ResizablePanelGroup orientation="horizontal" className="min-h-96 flex-1" defaultLayout={across.defaultLayout} onLayoutChanged={across.onLayoutChanged}>
      <ResizablePanel id="evidence" defaultSize="72">
        <ForecastPanel />
      </ResizablePanel>
      <ResizableHandle className={GAP_HANDLE} aria-label="Resize the situations panel" />
      <ResizablePanel id="situations" defaultSize="28" minSize="22" maxSize="42">
        <SituationsPanel />
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}

function StackedLayout() {
  return (
    <div className="flex shrink-0 flex-col gap-3">
      <SituationsPanel />
      <div className="h-[32rem]">
        <ForecastPanel />
      </div>
    </div>
  );
}

export function NowScreen() {
  const wide = useIsWide();
  return (
    <NowProvider>
      <KpiRow />
      {wide === null ? <Skeleton className="min-h-0 flex-1" /> : wide ? <WideLayout /> : <StackedLayout />}
      <SituationSheet />
    </NowProvider>
  );
}
