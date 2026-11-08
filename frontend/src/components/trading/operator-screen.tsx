"use client";

import { useQuery } from "@tanstack/react-query";
import { Eye, TriangleAlert } from "lucide-react";
import { type ReactNode, useMemo } from "react";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { queries } from "@/lib/api/queries";
import { formatClock, formatMegawatts, formatPrice, formatQuarterHours } from "@/lib/format";
import { costLevels, costLight, FUEL_LABELS, fuelRows, heatPlan, na4Messages, plantSide } from "@/lib/operator";
import { useViewingTime } from "@/lib/realtime/viewing-time";
import { cn } from "@/lib/utils";

import { useNow } from "./now-context";
import { NowScreen } from "./now-screen";
import { SkeletonLines } from "./panel";
import { PriceHistoryTable } from "./price-history";

const NONE: never[] = [];

/** NA4's rating in Nord Pool UMM. */
const NA4_MW = 145;

const TEXT = { green: "text-down", yellow: "text-warning", red: "text-error-text" } as const;
const RING = { review: "ring-2 ring-error", watch: "ring-2 ring-warning" } as const;

/** Ringed, with a "Look here" mark, when the situation in focus is about this part of the plant. */
function Figure({
  label,
  value,
  detail,
  tone,
  look,
}: {
  label: string;
  value: ReactNode;
  detail: ReactNode;
  tone?: keyof typeof TEXT;
  look?: "review" | "watch";
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-0.5 rounded-md px-2 py-1.5", look && RING[look])}>
      <p className="flex items-center justify-between gap-1 text-xs text-muted-foreground">
        <span className="truncate">{label}</span>
        {look ? <LookHere severity={look} /> : null}
      </p>
      <p className={cn("truncate text-xl font-semibold text-ink", tone && TEXT[tone])}>{value}</p>
      <p className="text-xs text-muted-foreground">{detail}</p>
    </div>
  );
}

function LookHere({ severity }: { severity: "review" | "watch" }) {
  return (
    <span className={cn("flex shrink-0 items-center gap-0.5 font-medium", severity === "review" ? "text-error-text" : "text-warning")}>
      {severity === "review" ? <TriangleAlert className="size-3" aria-hidden /> : <Eye className="size-3" aria-hidden />}
      Look here
    </span>
  );
}

/** Heat source and NA4 status, then NA4's fuels by power cost against the forecast. */
function FuelTab() {
  const { asOf } = useViewingTime();
  const forecast = useQuery(queries.forecast(asOf));
  const umm = useQuery(queries.umm(asOf));
  const fuel = useQuery(queries.fuel());
  const { selected } = useNow();

  const steps = forecast.data?.steps ?? NONE;
  if (fuel.isError) {
    return <p className="px-2 py-3 text-sm text-error-text">Fuel prices could not be loaded. Restart the API if it predates the fuel route.</p>;
  }
  if (!fuel.data || !forecast.data) return <SkeletonLines rows={6} className="px-2 py-2" />;

  const side = selected ? plantSide(selected, steps) : null;
  const look = (part: "heat" | "fuel") => (selected && side === part ? selected.severity : undefined);

  const breakEven = fuel.data.heat.e_boiler_cheaper_below_spot;
  const plan = heatPlan(steps, breakEven);
  const electric = plan.filter((source) => source === "electric").length;
  const origin = steps[0]?.delivery_start_utc ?? forecast.data.origin_utc;
  const na4 = na4Messages(umm.data?.messages ?? NONE);
  const out = na4.find((message) => message.event_start_utc <= origin && origin < message.event_stop_utc);
  const rows = fuelRows(fuel.data, steps);
  const lookFuel = look("fuel");

  return (
    <div className="flex flex-col gap-2 px-1 pb-1">
      <div className="grid grid-cols-2 gap-1">
        <Figure
          label="Heat source now"
          look={look("heat")}
          tone={plan[0] === "electric" ? "green" : plan[0] === "fuel" ? "yellow" : undefined}
          value={plan[0] === "electric" ? "E-boiler" : plan[0] === "fuel" ? "Chip boiler" : "–"}
          detail={
            <>
              Spot {formatPrice(steps[0]?.spot)}, break-even {formatPrice(breakEven)}
              <br />
              E-boiler cheaper {formatQuarterHours(electric)} of 10 h
            </>
          }
        />
        <Figure
          label="NA4"
          look={out ? (out.unplanned ? "review" : "watch") : undefined}
          tone={!umm.data?.available ? undefined : out ? "red" : "green"}
          value={!umm.data?.available ? "–" : out ? `${formatMegawatts(out.unavailable_mw)} out` : formatMegawatts(NA4_MW)}
          detail={
            <>
              {!umm.data?.available ? "Outage messages not loaded" : out ? (out.unplanned ? "Unplanned outage" : "Planned outage") : "Available"}
              <br />
              {out
                ? `Until ${formatClock(out.event_stop_utc)} UTC`
                : na4[0]
                  ? `Outage from ${formatClock(na4[0].event_start_utc)} UTC`
                  : "No outage message (UMM)"}
            </>
          }
        />
      </div>
      <div className={cn("rounded-md px-1", lookFuel && RING[lookFuel])}>
        {lookFuel ? (
          <p className="flex justify-end px-1 pt-1 text-xs">
            <LookHere severity={lookFuel} />
          </p>
        ) : null}
        <Table className="table-fixed text-xs">
          <colgroup>
            <col className="w-[34%]" />
            <col className="w-[22%]" />
            <col className="w-[22%]" />
            <col className="w-[22%]" />
          </colgroup>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="h-auto px-1.5 py-1.5">Fuel</TableHead>
              <TableHead className="h-auto px-1 py-1.5 text-right" title="Fuel price with CO2, € per MWh of fuel">
                Fuel €
              </TableHead>
              <TableHead className="h-auto px-1 py-1.5 text-right" title="NA4 power cost after heat credit, € per MWh of electricity">
                Power €
              </TableHead>
              <TableHead className="h-auto px-1.5 py-1.5 text-right" title="Hours of the next 10 with the forecast (P50) at or above the power cost">
                Pays
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => {
              const light = row.powerCost === null ? null : costLight(row.powerCost, steps);
              return (
                <TableRow key={row.fuel}>
                  <TableCell className="truncate px-1.5 py-1.5 text-ink">{FUEL_LABELS[row.fuel] ?? row.fuel}</TableCell>
                  <TableCell className="px-1 py-1.5 text-right tabular-nums">{formatPrice(row.fuelCost)}</TableCell>
                  <TableCell className={cn("px-1 py-1.5 text-right font-semibold tabular-nums", light ? TEXT[light] : "text-muted-foreground")}>
                    {formatPrice(row.powerCost)}
                  </TableCell>
                  <TableCell className="px-1.5 py-1.5 text-right tabular-nums">
                    {row.powerCost === null ? "–" : formatQuarterHours(row.coveredQuarters)}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
      <p className="px-2 text-xs text-muted-foreground">
        Power € green: paid by the average forecast, yellow: only by the peak, red: not at all. Statistics Finland
        {fuel.data.fuels.forest_chips?.period ? ` ${fuel.data.fuels.forest_chips.period}` : ""}, EUA {formatPrice(fuel.data.eua.eur_t)} €/t,
        placeholder efficiencies.
      </p>
    </div>
  );
}

/** Above the situations: the plant's fuel figures, with the Now screen's price history a tab away. */
function OperatorTabs() {
  return (
    <Tabs defaultValue="fuel" className="shrink-0 gap-1 border-b border-hairline-soft px-2 pt-3 pb-2">
      <div className="flex items-center justify-between gap-2 px-2">
        <h2 className="eyebrow text-stone">Naantali CHP</h2>
        <TabsList>
          <TabsTrigger value="fuel">Fuel</TabsTrigger>
          <TabsTrigger value="history">Price history</TabsTrigger>
        </TabsList>
      </div>
      <TabsContent value="fuel">
        <FuelTab />
      </TabsContent>
      <TabsContent value="history">
        <PriceHistoryTable />
      </TabsContent>
    </Tabs>
  );
}

/** The Now screen for the Naantali plant operator: the same chart and situations, with the plant's cost levels drawn on the chart. */
export function OperatorScreen() {
  const fuel = useQuery(queries.fuel());
  // Kept stable: the chart resets its view whenever its inputs change.
  const levels = useMemo(() => costLevels(fuel.data), [fuel.data]);
  return <NowScreen top={<OperatorTabs />} levels={levels} />;
}
