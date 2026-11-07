"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { queries } from "@/lib/api/queries";
import { formatDateTime, formatEuro, PRICE_UNIT } from "@/lib/format";
import { type Extreme, priceHistory } from "@/lib/price-history";
import { useViewingTime } from "@/lib/realtime/viewing-time";

import { SkeletonLines } from "./panel";
import { QueryState } from "./query-state";

/** Everything the store holds up to the viewing time. The chart and the table share this one request. */
function useHistory() {
  const { asOf } = useViewingTime();
  const forecast = useQuery(queries.forecast(asOf));
  const origin = forecast.data?.origin_utc;
  const history = useQuery({ ...queries.priceHistory(origin ?? "", asOf), enabled: origin !== undefined });
  return { origin, history };
}

/** Whole euros keep four price columns inside the narrow box; the hover text has the exact value and time. */
function Price({ value }: { value: Extreme | null }) {
  if (!value) return <span>–</span>;
  return <span title={`${formatEuro(value.price, { digits: 2 })} at ${formatDateTime(value.at)} UTC`}>{formatEuro(value.price, { digits: 0 })}</span>;
}

/** Price columns share one width and centre their contents, so each group name sits midway over its High and Low. */
const PRICE = "h-auto px-1 py-1.5 text-center";
const GROUP = "h-auto px-1 pt-1 pb-0.5 text-center";

/** Highest and lowest prices per period, set above the situations in the "What to check now" box. */
export function PriceHistorySection() {
  const { origin, history } = useHistory();
  const rows = useMemo(() => (history.data && origin ? priceHistory(history.data.points, origin) : []), [history.data, origin]);
  return (
    <section aria-labelledby="price-history-title" className="shrink-0 border-b border-hairline-soft px-2 pt-3 pb-2">
      <div className="flex items-baseline gap-2 px-2 pb-1">
        <h2 id="price-history-title" className="eyebrow text-stone">
          Price history
        </h2>
        <p className="truncate text-xs text-muted-foreground" title={`${PRICE_UNIT}. Hover a price for its exact value and time.`}>
          {PRICE_UNIT}
        </p>
      </div>
      <QueryState query={history} skeleton={<SkeletonLines rows={5} className="px-2" />}>
        {() => (
          <Table className="table-fixed text-xs">
            <colgroup>
              <col className="w-[24%]" />
              <col className="w-[19%]" />
              <col className="w-[19%]" />
              <col className="w-[19%]" />
              <col className="w-[19%]" />
            </colgroup>
            <TableHeader>
              <TableRow className="border-0 hover:bg-transparent">
                <TableHead rowSpan={2} className="h-auto px-1.5 align-bottom">
                  Period
                </TableHead>
                <TableHead colSpan={2} className={GROUP}>
                  <span className="block border-b border-hairline pb-0.5">Spot</span>
                </TableHead>
                <TableHead colSpan={2} className={GROUP}>
                  <span className="block border-b border-hairline pb-0.5">Imbalance</span>
                </TableHead>
              </TableRow>
              <TableRow className="hover:bg-transparent">
                <TableHead className={PRICE}>High</TableHead>
                <TableHead className={PRICE}>Low</TableHead>
                <TableHead className={PRICE}>High</TableHead>
                <TableHead className={PRICE}>Low</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.key}>
                  <TableCell className="truncate px-1.5 py-1.5 text-ink">{row.label}</TableCell>
                  <TableCell className={PRICE}>
                    <Price value={row.spotHigh} />
                  </TableCell>
                  <TableCell className={PRICE}>
                    <Price value={row.spotLow} />
                  </TableCell>
                  <TableCell className={PRICE}>
                    <Price value={row.imbalanceHigh} />
                  </TableCell>
                  <TableCell className={PRICE}>
                    <Price value={row.imbalanceLow} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </QueryState>
    </section>
  );
}
