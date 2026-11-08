import { ApiScreen } from "@/components/trading/api-screen";
import { DEFAULT_API_ORIGIN } from "@/lib/api-guide";

/**
 * Not /api: next.config.ts sends /api/* to the backend. The examples name the API's own address, read here
 * on the server, as scripts call it directly; the dashboard goes through its proxy.
 */
export default function ApiGuidePage() {
  return <ApiScreen origin={process.env.API_ORIGIN ?? DEFAULT_API_ORIGIN} />;
}
