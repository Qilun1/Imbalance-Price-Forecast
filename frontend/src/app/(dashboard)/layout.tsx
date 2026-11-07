import { cookies } from "next/headers";
import type { ReactNode } from "react";

import { AppShell } from "@/components/trading/app-shell";
import { SIDEBAR_COOKIE } from "@/components/trading/sidebar";
import { Providers } from "@/components/trading/providers";

/** The cookie lets the server draw the sidebar at its saved width, so it does not jump on load. */
export default async function DashboardLayout({ children }: { children: ReactNode }) {
  const startsAsRail = (await cookies()).get(SIDEBAR_COOKIE)?.value === "rail";
  return (
    <Providers>
      <AppShell startsAsRail={startsAsRail}>{children}</AppShell>
    </Providers>
  );
}
