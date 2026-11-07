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
  // A new storage id whenever the default split changes, so sizes saved for an older layout do not apply.
  const across = useDefaultLayout({ id: "now-across-v3", panelIds: ["evidence", "situations"], storage: safeStorage });
  return (
    // The height sits on a wrapper: the panel group sets its own height inline.
    <div className="min-h-[36rem] flex-1">
      <ResizablePanelGroup
        orientation="horizontal"
        className="h-full"
        defaultLayout={across.defaultLayout}
        onLayoutChanged={across.onLayoutChanged}
      >
        <ResizablePanel id="evidence" defaultSize="66">
          {/* The key figures sit above the chart, so their edges match it and the situations run full height. */}
          <div className="flex h-full min-h-0 flex-col gap-3">
            <KpiRow />
            <div className="min-h-0 flex-1">
              <ForecastPanel />
            </div>
          </div>
        </ResizablePanel>
        <ResizableHandle className={GAP_HANDLE} aria-label="Resize the situations panel" />
        <ResizablePanel id="situations" defaultSize="34" minSize="26" maxSize="45">
          <SituationsPanel />
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}

function StackedLayout() {
  return (
    <div className="flex shrink-0 flex-col gap-3">
      <KpiRow />
      {/* The wrappers keep each box's own height: directly in this column, its h-full would span the page. */}
      <div className="shrink-0">
        <SituationsPanel />
      </div>
      <div className="h-[56rem] shrink-0">
        <ForecastPanel />
      </div>
    </div>
  );
}

export function NowScreen() {
  const wide = useIsWide();
  return (
    <NowProvider>
      {wide === null ? <Skeleton className="min-h-0 flex-1" /> : wide ? <WideLayout /> : <StackedLayout />}
      <SituationSheet />
    </NowProvider>
  );
}
