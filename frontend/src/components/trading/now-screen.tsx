"use client";

import { useDefaultLayout } from "react-resizable-panels";

import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { Skeleton } from "@/components/ui/skeleton";
import { safeStorage, useIsWide } from "@/lib/browser";

import { NowProvider } from "./now-context";
import { ChangesPanel, DriversPanel, ForecastPanel, KpiRow } from "./now-panels";
import { PageHeader } from "./page-header";
import { SituationSheet } from "./situation-sheet";
import { SituationsPanel } from "./situations";

const GAP_HANDLE = "w-3 bg-transparent aria-[orientation=horizontal]:h-3 aria-[orientation=horizontal]:w-full";

function WideLayout() {
  const across = useDefaultLayout({ id: "now-across", panelIds: ["situations", "evidence"], storage: safeStorage });
  const down = useDefaultLayout({ id: "now-down", panelIds: ["forecast", "detail"], storage: safeStorage });
  return (
    <ResizablePanelGroup orientation="horizontal" className="min-h-96 flex-1" defaultLayout={across.defaultLayout} onLayoutChanged={across.onLayoutChanged}>
      <ResizablePanel id="situations" defaultSize="28" minSize="22" maxSize="42">
        <SituationsPanel />
      </ResizablePanel>
      <ResizableHandle className={GAP_HANDLE} aria-label="Resize the situations panel" />
      <ResizablePanel id="evidence" defaultSize="72">
        <ResizablePanelGroup orientation="vertical" defaultLayout={down.defaultLayout} onLayoutChanged={down.onLayoutChanged}>
          <ResizablePanel id="forecast" defaultSize="67" minSize="45">
            <ForecastPanel />
          </ResizablePanel>
          <ResizableHandle className={GAP_HANDLE} aria-label="Resize the forecast panel" />
          <ResizablePanel id="detail" defaultSize="33" minSize="18">
            <div className="grid h-full grid-cols-2 gap-3">
              <DriversPanel />
              <ChangesPanel />
            </div>
          </ResizablePanel>
        </ResizablePanelGroup>
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
      <div className="grid gap-3 md:grid-cols-2">
        <DriversPanel />
        <ChangesPanel />
      </div>
    </div>
  );
}

export function NowScreen() {
  const wide = useIsWide();
  return (
    <NowProvider>
      <PageHeader title="What to check now" />
      <KpiRow />
      {wide === null ? <Skeleton className="min-h-0 flex-1" /> : wide ? <WideLayout /> : <StackedLayout />}
      <SituationSheet />
    </NowProvider>
  );
}
