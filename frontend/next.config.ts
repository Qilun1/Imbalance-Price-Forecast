import type { NextConfig } from "next";

const API_ORIGIN = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

const config: NextConfig = {
  agentRules: false, // the repo's root AGENTS.md is the only rule file
  devIndicators: false,
  // On real data the API builds every forecast's alerts for about 30 s after start-up; a history request
  // in that window can take longer than the proxy's 30 s default and would come back as a hang-up.
  experimental: { proxyTimeout: 120_000 },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
};

export default config;
