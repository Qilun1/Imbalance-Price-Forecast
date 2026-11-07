"use client";

import { useQuery } from "@tanstack/react-query";
import { CircleDashed } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { queries } from "@/lib/api/queries";
import { useViewingTime } from "@/lib/realtime/viewing-time";

import { ExposureCheck } from "./exposure-check";
import { DensityToggle, ForecastTable, useDensity } from "./forecast-table";
import { PageHeader } from "./page-header";
import { Panel, PanelBody, PanelHeader, PanelMessage } from "./panel";
import { QueryState } from "./query-state";

const NONE: never[] = [];

export function NextScreen() {
  const { asOf } = useViewingTime();
  const forecast = useQuery(queries.forecast(asOf));
  const changes = useQuery(queries.changes(asOf));
  const alerts = useQuery(queries.alerts(asOf));
  const [density, setDensity] = useDensity();
  const [checking, setChecking] = useState(false);

  return (
    <>
      <PageHeader title="Next 10 hours">
        <Button variant="primary" className="hidden md:inline-flex" disabled={!forecast.data?.steps.length} onClick={() => setChecking(true)}>
          Exposure check
        </Button>
      </PageHeader>
      <Panel label="Forecast by quarter-hour" className="min-h-96 flex-1">
        <PanelHeader title="Quarter-hours" note="Prices in €/MWh, times in UTC. Change is since the previous update.">
          <DensityToggle density={density} onChange={setDensity} />
        </PanelHeader>
        <PanelBody className="px-1 pb-1">
          <QueryState
            query={forecast}
            isEmpty={(data) => data.steps.length === 0}
            empty={
              <PanelMessage icon={CircleDashed} title="No forecast at this time">
                Step to another hour, or go back to the latest forecast.
              </PanelMessage>
            }
            skeleton={
              <div className="flex flex-col gap-2 px-3" aria-hidden>
                {Array.from({ length: 12 }, (_, index) => (
                  <Skeleton key={index} className="h-6 w-full" />
                ))}
              </div>
            }
          >
            {(data) => <ForecastTable forecast={data} changes={changes.data} density={density} />}
          </QueryState>
        </PanelBody>
      </Panel>
      <Sheet open={checking} onOpenChange={setChecking}>
        <SheetContent className="w-full gap-0 sm:max-w-md data-[side=right]:sm:max-w-md">
          <SheetHeader className="gap-1 border-b p-4 pr-12">
            <SheetTitle className="text-lg font-medium">Exposure check</SheetTitle>
            <SheetDescription>What an open position could cost compared with spot.</SheetDescription>
          </SheetHeader>
          <div className="scrollbar-thin min-h-0 flex-1 overflow-auto p-4">
            {forecast.data ? <ExposureCheck forecast={forecast.data} alerts={alerts.data?.alerts ?? NONE} /> : null}
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
