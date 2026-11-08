import { describe, expect, it } from "vitest";

import { DEFAULT_API_ORIGIN, ENDPOINTS, pullExample } from "@/lib/api-guide";

describe("API screen", () => {
  it("pulls from the API's own address and never prints the spot price", () => {
    const code = pullExample(DEFAULT_API_ORIGIN);
    expect(code.split("\n")[0]).toBe('$api = "http://127.0.0.1:8000/api"');
    expect(code).toContain("Format-Table delivery_start_utc, p10, p50, p90");
    expect(code).not.toMatch(/\bspot\b/);
  });

  it("lists only API paths", () => {
    expect(ENDPOINTS.map((endpoint) => endpoint.path)).toEqual(["/api/forecast", "/api/alerts", "/api/hindsight", "/api/meta"]);
  });
});
