"use client";

/**
 * There is no stream to subscribe to: a forecast is made once an hour. Polling /api/meta tells whether
 * the API is reachable, and whether a newer forecast has arrived.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { toast } from "sonner";

import { queries } from "@/lib/api/queries";

type Connection = "live" | "reconnecting" | "offline";

function useConnection(): Connection {
  const { isError, isPending, fetchStatus, failureCount } = useQuery(queries.meta());
  if (isError) return fetchStatus === "fetching" ? "reconnecting" : "offline";
  if (isPending || failureCount > 0) return "reconnecting";
  return "live";
}

/** Tells the viewer when the connection changes and refreshes data once it returns. */
export function useConnectionEvents(): void {
  const connection = useConnection();
  const queryClient = useQueryClient();
  const { data: meta } = useQuery(queries.meta());
  const previous = useRef<Connection>(connection);
  const newest = useRef(meta?.last_origin_utc);

  useEffect(() => {
    // "Reconnecting" sits between the two states that matter, so it must not overwrite them.
    if (connection === "reconnecting") return;
    const before = previous.current;
    previous.current = connection;
    if (before === connection) return;
    if (connection === "offline") {
      toast.error("Connection lost", { description: "Showing the last data received." });
    } else if (before === "offline") {
      toast.success("Connection restored");
      void queryClient.invalidateQueries({ predicate: (query) => query.state.status === "error" });
    }
  }, [connection, queryClient]);

  useEffect(() => {
    const origin = meta?.last_origin_utc;
    if (origin && newest.current && origin !== newest.current) {
      void queryClient.invalidateQueries({ predicate: (query) => query.queryKey.includes("latest") });
    }
    newest.current = origin;
  }, [meta?.last_origin_utc, queryClient]);
}
