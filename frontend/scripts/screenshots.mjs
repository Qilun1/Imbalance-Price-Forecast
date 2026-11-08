/*
 * The prompt's verification loop: every screen, width and state, into frontend/screenshots (gitignored).
 * Mock mode only. Real spot prices must never end up in shared output (AGENTS.md rule 6), so this stops
 * if the API reports real data.
 *
 *   node scripts/screenshots.mjs                                  everything
 *   node scripts/screenshots.mjs --widths 1440 --states populated --screens now
 *   node scripts/screenshots.mjs --at 2026-10-23T09:00:00Z        a chosen viewing time
 */
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const out = join(root, "screenshots");
const base = process.env.BASE_URL ?? "http://localhost:3000";

function option(name, fallback) {
  const index = process.argv.indexOf(`--${name}`);
  return index > -1 ? process.argv[index + 1] : fallback;
}

const SCREENS = { now: "/", next: "/next-10h", hindsight: "/hindsight", api: "/api-guide" };
const STATES = { populated: "", loading: "fault=loading", empty: "fault=empty", error: "fault=error", offline: "fault=offline" };
const HEIGHTS = { 768: 1024, 1280: 800, 1440: 900, 1920: 1080 };

const screens = option("screens", Object.keys(SCREENS).join(",")).split(",");
const states = option("states", Object.keys(STATES).join(",")).split(",");
const widths = option("widths", "1280,1440,1920,768").split(",").map(Number);
const at = option("at", "2026-10-23T09:00:00Z");

const meta = await (await fetch(`${base}/api/meta`)).json();
if (meta.mode !== "mock") {
  console.error("The API is serving real data. Screenshots run on mock mode only (AGENTS.md rule 6).");
  process.exit(1);
}

mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ channel: "msedge" });
let failures = 0;

for (const width of widths) {
  const context = await browser.newContext({ viewport: { width, height: HEIGHTS[width] ?? 900 } });
  const page = await context.newPage();
  const problems = [];
  page.on("pageerror", (error) => problems.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error" && !message.text().includes("favicon")) problems.push(message.text());
  });
  for (const screen of screens) {
    for (const state of states) {
      const query = [`as_of=${at}`, STATES[state]].filter(Boolean).join("&");
      await page.goto(`${base}${SCREENS[screen]}?${query}`, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout({ populated: 1500, error: 4000, offline: 4000 }[state] ?? 900);
      const file = join(out, `${screen}-${state}-${width}.png`);
      await page.screenshot({ path: file });
      const expected = state === "error" || state === "offline";
      const shown = expected ? [] : problems.filter((text) => !text.includes("Failed to load resource"));
      console.log(`${screen} ${state} ${width}${shown.length ? `  PROBLEM: ${shown[0].slice(0, 160)}` : ""}`);
      failures += shown.length ? 1 : 0;
      problems.length = 0;
    }
  }
  await context.close();
}

await browser.close();
process.exit(failures ? 1 : 0);
