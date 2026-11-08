import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { fraunces, inter, jetbrainsMono } from "./fonts";
import "./globals.css";

export const metadata: Metadata = {
  title: "Volta · Imbalance price forecast",
  description: "What to check now and in the next 10 hours in the Finnish imbalance market.",
};

/** The canvas token. Browsers read this before any CSS has loaded. */
export const viewport: Viewport = { themeColor: "#f7f1e8" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${fraunces.variable} ${inter.variable} ${jetbrainsMono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
