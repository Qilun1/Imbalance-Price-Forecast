/**
 * The frontend half of the mock adapter. The backend's seeded mock mode is the one source of invented
 * data. This wrapper adds what data alone cannot show: slow answers, errors, a lost connection and empty
 * responses, so every panel state can be seen and tested.
 *
 * Add ?fault=slow|loading|error|offline|empty to the URL. It works under `next dev`, and in a build made
 * with NEXT_PUBLIC_API_FAULTS=on. Production builds ignore it.
 */
import { ApiError, NOT_ANSWERING } from "./errors";

export type Fault = "slow" | "loading" | "error" | "offline" | "empty";

const FAULTS: readonly string[] = ["slow", "loading", "error", "offline", "empty"];
const SLOW_MS = 1500;

const enabled = process.env.NODE_ENV === "development" || process.env.NEXT_PUBLIC_API_FAULTS === "on";

function activeFault(): Fault | null {
  if (!enabled || typeof window === "undefined") return null;
  const value = new URLSearchParams(window.location.search).get("fault");
  return value !== null && FAULTS.includes(value) ? (value as Fault) : null;
}

/** Every list in a response becomes empty; the fields around it stay. */
function emptied<T>(value: T): T {
  if (Array.isArray(value)) return [] as T;
  if (value === null || typeof value !== "object") return value;
  return Object.fromEntries(Object.entries(value).map(([key, field]) => [key, emptied(field)])) as T;
}

export async function applyFault<T>(call: () => Promise<T>): Promise<T> {
  switch (activeFault()) {
    case "slow":
      await new Promise((resolve) => setTimeout(resolve, SLOW_MS));
      return call();
    case "loading":
      return new Promise<T>(() => undefined);
    case "error":
      throw new ApiError(NOT_ANSWERING, 500);
    case "offline":
      throw new ApiError(NOT_ANSWERING, null);
    case "empty":
      return emptied(await call());
    default:
      return call();
  }
}
