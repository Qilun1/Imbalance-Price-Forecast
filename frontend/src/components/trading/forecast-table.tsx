"use client";

import {
  columnResizingFeature,
  columnSizingFeature,
  createColumnHelper,
  createSortedRowModel,
  rowSortingFeature,
  sortFn_basic,
  sortFn_datetime,
  type SortingState,
  tableFeatures,
  useTable,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import { useMemo, useState } from "react";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Changes, Forecast, ForecastStep } from "@/lib/api/client";
import { formatClock, formatDate, formatPercent, formatPrice, formatSignedPrice, formatWeekday, NO_VALUE } from "@/lib/format";
import { directionOf, spread } from "@/lib/forecast";
import { cn } from "@/lib/utils";

import { DirectionLabel, PriceCell } from "./cells";

type Row = ForecastStep & { spread: number | null; change: number | null; firstOfDay: boolean };

const features = tableFeatures({
  rowSortingFeature,
  columnSizingFeature,
  columnResizingFeature,
  sortedRowModel: createSortedRowModel(),
  sortFns: { basic: sortFn_basic, datetime: sortFn_datetime },
  columnMeta: {} as { numeric?: boolean },
});

const helper = createColumnHelper<typeof features, Row>();
const number = { sortFn: "basic", sortUndefined: "last", meta: { numeric: true } } as const;

const COLUMNS = helper.columns([
  helper.accessor("delivery_start_utc", {
    header: "Time",
    size: 96,
    sortFn: "datetime",
    cell: ({ row }) => (
      <span className="flex items-baseline gap-2">
        <span className="font-medium text-ink">{formatClock(row.original.delivery_start_utc)}</span>
        {row.original.firstOfDay ? <span className="text-xs text-muted-foreground">{formatWeekday(row.original.delivery_start_utc)}</span> : null}
      </span>
    ),
  }),
  helper.accessor("spot", { ...number, header: "Spot", size: 72, cell: ({ getValue }) => formatPrice(getValue()) }),
  helper.accessor("p10", { ...number, header: "P10", size: 72, cell: ({ getValue }) => formatPrice(getValue()) }),
  helper.accessor("p50", {
    ...number,
    header: "P50",
    size: 72,
    cell: ({ getValue }) => <PriceCell value={getValue()} live className="font-medium text-ink" />,
  }),
  helper.accessor("p90", { ...number, header: "P90", size: 72, cell: ({ getValue }) => formatPrice(getValue()) }),
  helper.accessor("spread", { ...number, header: "P50 vs spot", size: 104, cell: ({ getValue }) => formatSignedPrice(getValue()) }),
  helper.display({
    id: "direction",
    header: "Direction",
    size: 116,
    cell: ({ row }) => <DirectionLabel direction={directionOf(row.original)} />,
  }),
  helper.accessor("p_up", { ...number, header: "Up", size: 64, cell: ({ getValue }) => formatPercent(getValue()) }),
  helper.accessor("p_down", { ...number, header: "Down", size: 72, cell: ({ getValue }) => formatPercent(getValue()) }),
  helper.accessor("p_spike_high", { ...number, header: "High risk", size: 88, cell: ({ getValue }) => formatPercent(getValue()) }),
  helper.accessor("p_spike_low", { ...number, header: "Low risk", size: 84, cell: ({ getValue }) => formatPercent(getValue()) }),
  helper.accessor("change", { ...number, header: "Change", size: 80, cell: ({ getValue }) => formatSignedPrice(getValue()) }),
  helper.display({
    id: "drivers",
    header: "Main factors",
    size: 200,
    cell: ({ row }) => {
      const text = row.original.drivers.map((driver) => driver.label).join(", ");
      if (!text) return NO_VALUE;
      return (
        <Tooltip>
          <TooltipTrigger asChild>
            <span tabIndex={0} className="block truncate rounded-xs text-stone">
              {text}
            </span>
          </TooltipTrigger>
          <TooltipContent className="max-w-sm">{text}</TooltipContent>
        </Tooltip>
      );
    },
  }),
]);

function SortIcon({ sorted }: { sorted: false | "asc" | "desc" }) {
  if (sorted === "asc") return <ArrowUp className="size-3" aria-hidden />;
  if (sorted === "desc") return <ArrowDown className="size-3" aria-hidden />;
  return <ChevronsUpDown className="size-3 opacity-50" aria-hidden />;
}

export function ForecastTable({ forecast, changes }: { forecast: Forecast; changes: Changes | undefined }) {
  const rows = useMemo<Row[]>(() => {
    const byTime = new Map(changes?.points.map((point) => [point.delivery_start_utc, point.p50_change]));
    return forecast.steps.map((step, index) => {
      const previous = forecast.steps[index - 1];
      return {
        ...step,
        spread: spread(step),
        change: byTime.get(step.delivery_start_utc) ?? null,
        firstOfDay: !previous || formatDate(previous.delivery_start_utc) !== formatDate(step.delivery_start_utc),
      };
    });
  }, [forecast, changes]);
  const [sorting, setSorting] = useState<SortingState>([]);

  const table = useTable({
    features,
    columns: COLUMNS,
    data: rows,
    state: { sorting },
    onSortingChange: setSorting,
    columnResizeMode: "onChange",
    getRowId: (row) => row.delivery_start_utc,
  });

  return (
    <Table
      className="table-fixed"
      containerClassName="scrollbar-thin h-full overflow-auto"
      style={{
        width: table.getTotalSize(),
        minWidth: "100%",
        ["--table-row-height" as string]: "var(--spacing-row-comfortable)",
      }}
    >
      <TableHeader className="sticky top-0 z-10 bg-card">
        {table.getHeaderGroups().map((group) => (
          <TableRow key={group.id} className="hover:bg-transparent">
            {group.headers.map((header) => {
              const numeric = header.column.columnDef.meta?.numeric === true;
              const sorted = header.column.getIsSorted();
              return (
                <TableHead
                  key={header.id}
                  style={{ width: header.column.id === "drivers" ? undefined : header.getSize() }}
                  aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : undefined}
                  className={cn("relative", numeric && "text-right", header.column.id === "direction" && "pl-6")}
                >
                  {header.column.getCanSort() ? (
                    <button
                      type="button"
                      onClick={header.column.getToggleSortingHandler()}
                      className={cn("eyebrow inline-flex items-center gap-1 rounded-xs after:absolute after:inset-0", numeric && "flex-row-reverse")}
                    >
                      <table.FlexRender header={header} />
                      <SortIcon sorted={sorted} />
                    </button>
                  ) : (
                    <table.FlexRender header={header} />
                  )}
                  <span
                    role="presentation"
                    onMouseDown={header.getResizeHandler()}
                    onTouchStart={header.getResizeHandler()}
                    onDoubleClick={() => header.column.resetSize()}
                    className="absolute inset-y-1 right-0 z-10 w-2 cursor-col-resize touch-none border-r border-transparent hover:border-control-border"
                  />
                </TableHead>
              );
            })}
          </TableRow>
        ))}
      </TableHeader>
      <TableBody>
        {table.getRowModel().rows.map((row) => (
          <TableRow key={row.id}>
            {row.getAllCells().map((cell) => (
              <TableCell
                key={cell.id}
                className={cn("overflow-hidden", cell.column.columnDef.meta?.numeric === true && "text-right", cell.column.id === "direction" && "pl-6")}
              >
                <table.FlexRender cell={cell} />
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
