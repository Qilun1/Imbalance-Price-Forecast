import type { NextConfig } from "next";

const API_ORIGIN = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

const config: NextConfig = {
  agentRules: false, // the repo's root AGENTS.md is the only rule file
  devIndicators: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` }];
  },
};

export default config;
