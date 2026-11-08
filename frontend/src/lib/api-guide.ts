/**
 * The API screen, essentials only: how to pull from the API once it runs in real mode on the model's
 * forecasts (docs/LIVE_DEPLOYMENT.md, step 4).
 *
 * Spot (AGENTS.md rule 6): on real data /forecast, /actuals and /hindsight carry the licensed Nord Pool
 * spot price, so the example names the forecast fields it prints.
 */

/** Where scripts reach the API when API_ORIGIN is not set: the same default as next.config.ts. */
export const DEFAULT_API_ORIGIN = "http://127.0.0.1:8000";

export const ENDPOINTS: readonly { path: string; returns: string }[] = [
  { path: "/api/forecast", returns: "The next 10 hours: the price with its P10–P90 interval, and the chances of each direction and of a spike" },
  { path: "/api/alerts", returns: "The situations worth checking now" },
  { path: "/api/hindsight", returns: "Past forecasts beside what happened" },
  { path: "/api/meta", returns: "The data and model the API serves" },
];

/** Names the forecast fields it prints, so the spot price in the same answer is never printed. */
export function pullExample(origin: string): string {
  return [
    `$api = "${origin}/api"`,
    '(Invoke-RestMethod "$api/alerts").alerts | Format-List title, message',
    '(Invoke-RestMethod "$api/forecast").steps |',
    "    Format-Table delivery_start_utc, p10, p50, p90, p_up, p_down",
  ].join("\n");
}
