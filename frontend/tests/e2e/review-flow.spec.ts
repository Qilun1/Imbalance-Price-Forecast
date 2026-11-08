import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

const SPIKE = "2026-10-23T09:00:00Z"; // scripted in backend/api/mock.py
const SCREENS = ["/", "/next-10h", "/hindsight", "/api-guide"];

test.beforeAll(async ({ request }) => {
  const meta = await (await request.get("/api/meta")).json();
  expect(meta.mode, "e2e tests run on mock data only (AGENTS.md rule 6)").toBe("mock");
});

async function quietHour(page: Page): Promise<string> {
  const history = await (await page.request.get("/api/alerts/history")).json();
  const busy = new Set<string>(history.hours.map((hour: { origin_utc: string }) => hour.origin_utc));
  const meta = await (await page.request.get("/api/meta")).json();
  let time = new Date(meta.first_origin_utc).getTime() + 3_600_000;
  while (busy.has(new Date(time).toISOString().replace(".000Z", "Z"))) time += 3_600_000;
  return new Date(time).toISOString().replace(".000Z", "Z");
}

test("reviewing a situation, from a calm hour to hindsight", async ({ page }) => {
  await page.goto(`/?as_of=${await quietHour(page)}`);
  await expect(page.getByText("Nothing to check")).toBeVisible();

  await page.goto(`/?as_of=${SPIKE}`);
  await expect(page.getByRole("heading", { name: "What to check now" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Worth an expert review/ })).toHaveAttribute("aria-pressed", "true");

  await page.getByRole("button", { name: /Risk of an exceptionally high price/ }).click();
  await expect(page.getByRole("button", { name: /Risk of an exceptionally high price/ })).toHaveAttribute("aria-pressed", "true");

  await page.getByRole("button", { name: "Review situation" }).click();
  const sheet = page.getByRole("dialog");
  await expect(sheet.getByText("Worth checking", { exact: true })).toBeVisible();
  await expect(sheet.getByText("How it developed")).toBeVisible();
  await expect(sheet.getByRole("img")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden();

  await page.getByRole("switch", { name: "Show what happened" }).click();
  await expect(page.getByRole("switch", { name: "Show what happened" })).toBeChecked();

  await page.getByRole("main").click({ position: { x: 4, y: 4 } });
  await page.keyboard.press("ArrowRight");
  await expect(page).toHaveURL(/as_of=2026-10-23T10%3A00%3A00Z|as_of=2026-10-23T10:00:00Z/);
  await page.keyboard.press("Shift+ArrowLeft");
  await expect(page).toHaveURL(/as_of=2026-10-22T10/);

  await page.keyboard.press("2");
  await expect(page.getByRole("heading", { name: "Next 10 hours" })).toBeVisible();
  await expect(page).toHaveURL(/as_of=2026-10-22T10/);
  await expect(page.locator("tbody tr")).toHaveCount(40);

  await page.getByRole("button", { name: "Exposure check" }).click();
  const check = page.getByRole("dialog");
  await check.getByRole("button", { name: "Estimate" }).click();
  await expect(check.getByText("Enter a size in MW.")).toBeVisible();
  await check.getByLabel("Size, MW").fill("abc");
  await check.getByRole("button", { name: "Estimate" }).click();
  await expect(check.getByText("Enter a number.")).toBeVisible();
  await check.getByLabel("Size, MW").fill("2,5");
  await check.getByRole("button", { name: "Estimate" }).click();
  await expect(check.getByRole("status")).toContainText("Short 2.5 MW");
  await expect(check.getByRole("status")).toContainText("compared with spot");
  await page.keyboard.press("Escape");

  await page.goto(`/hindsight?as_of=2026-10-28T20:00:00Z`);
  await expect(page.getByRole("heading", { name: "Hindsight" })).toBeVisible();
  await page.getByRole("radio", { name: "Previous day" }).click();
  await expect(page).toHaveURL(/range=day/);
  const firstRaised = page.getByRole("region", { name: "Situations raised in this period" }).getByRole("button").first();
  await firstRaised.click();
  await expect(page).not.toHaveURL(/as_of=2026-10-28T20/);

  await page.getByRole("main").click({ position: { x: 4, y: 4 } });
  await page.keyboard.press("l");
  await expect(page).not.toHaveURL(/as_of=/);
});

test("there is no top bar on a wide screen", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/?as_of=${SPIKE}`);
  await expect(page.getByRole("heading", { name: "What to check now" })).toBeVisible();
  await expect(page.getByRole("banner")).toHaveCount(0);
  await expect(page.getByRole("group", { name: "Viewing time" })).toHaveCount(0);
  await expect(page.getByText("Forecast made")).toHaveCount(0);
});

test("page content reads in UTC", async ({ page }) => {
  await page.goto(`/next-10h?as_of=${SPIKE}`);
  await expect(page.locator("tbody tr").first()).toContainText("09:00");
  await expect(page.getByText("times in UTC")).toBeVisible();

  await page.goto(`/?as_of=${SPIKE}`);
  const card = page.getByRole("button", { name: /Worth an expert review/ });
  await expect(card).toContainText("13:00–15:00");
  await expect(card).toContainText("for 13:00–15:00 UTC");
});

test("no chart panel names TradingView, and the licence notice stays reachable", async ({ page }) => {
  await page.goto(`/?as_of=${SPIKE}`);
  await expect(page.getByRole("button", { name: "Review situation" })).toBeVisible();
  await expect(page.getByText("Charts by TradingView")).toHaveCount(0);
  await page.keyboard.press("?");
  await expect(page.getByRole("dialog").getByRole("link", { name: /TradingView Lightweight Charts/ })).toHaveAttribute("href", "https://www.tradingview.com/");
});

for (const width of [1280, 1440, 1920]) {
  test(`the situation log shows whole titles in the side box at ${width} px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/hindsight?as_of=2026-10-28T20:00:00Z&range=week");
    const log = page.getByRole("region", { name: "Situations raised in this period" });
    await expect(log.getByText("Forecast changed since the previous update", { exact: true }).first()).toBeVisible();
    const fits = await log.locator("[data-slot=situation-log]").evaluate((box) => box.scrollWidth <= box.clientWidth);
    expect(fits, "no column is pushed out of sight").toBe(true);
  });
}

test("the command menu and shortcuts open from the keyboard", async ({ page }) => {
  await page.goto(`/?as_of=${SPIKE}`);
  await expect(page.getByRole("button", { name: /Worth an expert review/ })).toBeVisible();
  await page.keyboard.press("Control+k");
  const menu = page.getByRole("dialog");
  await expect(menu.getByPlaceholder("Type a command…")).toBeVisible();
  await menu.getByPlaceholder("Type a command…").fill("hindsight");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Hindsight" })).toBeVisible();

  await page.keyboard.press("?");
  await expect(page.getByRole("dialog").getByText("Keyboard shortcuts")).toBeVisible();
});

test("replay moves the viewing time forward and pauses", async ({ page }) => {
  await page.goto(`/?as_of=${SPIKE}`);
  await expect(page.getByRole("button", { name: "Review situation" })).toBeVisible();
  await page.getByRole("main").click({ position: { x: 4, y: 4 } });
  await page.keyboard.press("r");
  await expect(page).toHaveURL(/as_of=2026-10-23T1[01]/, { timeout: 5000 });
  await page.keyboard.press("r");
  const paused = page.url();
  await page.waitForTimeout(2500);
  expect(page.url()).toBe(paused);
});

test("past situations show whether they came true", async ({ page }) => {
  await page.goto("/hindsight?as_of=2026-10-28T20:00:00Z&range=week");
  await expect(page.getByText("Happened", { exact: true }).first()).toBeVisible();
  await page.goto("/hindsight?as_of=2026-10-23T09:00:00Z");
  await expect(page.getByText("Not known yet", { exact: true }).first()).toBeVisible();
});

test("shortcuts stay quiet while typing", async ({ page }) => {
  await page.goto(`/next-10h?as_of=${SPIKE}`);
  await page.getByRole("button", { name: "Exposure check" }).click();
  await page.getByLabel("Size, MW").fill("2");
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("l");
  await expect(page).toHaveURL(/as_of=2026-10-23T09/);
});

test("the states a panel can be in", async ({ page }) => {
  await page.goto(`/?as_of=${SPIKE}&fault=error`);
  await expect(page.getByText("This could not be loaded").first()).toBeVisible();

  await page.goto(`/?fault=offline`);
  await expect(page.getByText("Connection lost")).toBeVisible();

  await page.goto(`/?as_of=${SPIKE}&fault=empty`);
  await expect(page.getByText("Nothing to check")).toBeVisible();
  await expect(page.getByText("No forecast at this time")).toBeVisible();
});

test("losing and regaining the API is announced", async ({ page }) => {
  await page.clock.install();
  await page.goto(`/?as_of=${SPIKE}`);
  await expect(page.getByRole("button", { name: "Review situation" })).toBeVisible();

  await page.route("**/api/**", (route) => route.abort());
  await page.clock.fastForward(61_000);
  await page.clock.runFor(2_000);
  await expect(page.getByText("Connection lost")).toBeVisible();
  await expect(page.getByRole("button", { name: "Review situation" }), "the last data stays on screen").toBeVisible();

  await page.unroute("**/api/**");
  await page.clock.fastForward(11_000);
  await page.clock.runFor(2_000);
  await expect(page.getByText("Connection restored")).toBeVisible();
});

test("the arrow keys read the chart one quarter-hour at a time", async ({ page }) => {
  await page.goto(`/?as_of=${SPIKE}`);
  const time = page.locator("[data-field=time]");
  await expect(time).toHaveText("23 Oct 09:00");
  await page.getByRole("img", { name: /Forecast chart/ }).focus();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await expect(time).toHaveText("23 Oct 09:15");
  await expect(page.locator("[data-field=direction]")).toContainText(/up <?\d+%/);
  await page.keyboard.press("Escape");
  await expect(time).toHaveText("23 Oct 09:00");
});

test("a key figure shows its time in the chart, and pressing it again lets go", async ({ page }) => {
  await page.goto(`/?as_of=${SPIKE}`);
  const time = page.locator("[data-field=time]");
  await expect(time).toHaveText("23 Oct 09:00");
  // A figure brings the history back to one day.
  await page.getByRole("radio", { name: "1 week" }).click();
  await expect(page.getByRole("radio", { name: "1 week" })).toHaveAttribute("data-state", "on");
  const highest = page.getByRole("button", { name: "Show the highest price in the chart" });
  const at = await highest.locator("xpath=..").getByText(/^At \d\d:\d\d$/).textContent();
  await highest.click();
  await expect(highest).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("radio", { name: "1 day" })).toHaveAttribute("data-state", "on");
  await expect(time).toContainText(at?.replace("At ", "") ?? "missing");
  await highest.click();
  await expect(highest).toHaveAttribute("aria-pressed", "false");
  await expect(time).toHaveText("23 Oct 09:00");
});

test("the API page says how to pull from the API", async ({ page }) => {
  await page.goto(`/?as_of=${SPIKE}`);
  await expect(page.getByRole("button", { name: /Worth an expert review/ })).toBeVisible();
  await page.getByRole("main").click({ position: { x: 4, y: 4 } });
  await page.keyboard.press("4");
  await expect(page.getByRole("heading", { name: "API", level: 1 })).toBeVisible();
  await expect(page).toHaveURL(/\/api-guide\?as_of=2026-10-23T09/);

  await expect(page.getByText("Serving", { exact: false })).toHaveCount(0);
  const pull = page.getByRole("region", { name: "Pull the data" });
  await expect(pull.locator("tbody tr")).toHaveCount(4);
  await expect(pull.locator("pre")).toContainText("Format-Table delivery_start_utc, p10, p50, p90");
  await expect(pull.locator("pre")).not.toContainText("spot");
});

test("a viewing time outside the data offers a way back", async ({ page }) => {
  await page.goto("/?as_of=2020-01-01T00:00:00Z");
  await expect(page.getByRole("button", { name: "Back to latest" }).first()).toBeVisible();
  await expect(page.getByText("This could not be loaded").first()).toBeVisible();
});

for (const path of SCREENS) {
  test(`${path} has at most one blue action and no accessibility problems`, async ({ page }) => {
    await page.goto(`${path}?as_of=${SPIKE}`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.locator("tbody tr, [aria-pressed], [data-slot=situation-log] li").first()).toBeVisible();
    await page.waitForTimeout(800);
    expect(await page.locator('[data-variant="primary"]').count()).toBeLessThanOrEqual(1);
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
    const problems = results.violations.map((violation) => `${violation.id}: ${violation.nodes.length} (${violation.nodes[0]?.target})`);
    expect(problems).toEqual([]);
  });
}

test("the Review sheet has no accessibility problems", async ({ page }) => {
  await page.goto(`/?as_of=${SPIKE}`);
  await page.getByRole("button", { name: "Review situation" }).click();
  await expect(page.getByText("How it developed")).toBeVisible();
  await page.waitForTimeout(800);
  const results = await new AxeBuilder({ page }).include('[role="dialog"]').withTags(["wcag2a", "wcag2aa", "wcag22aa"]).analyze();
  expect(results.violations.map((violation) => violation.id)).toEqual([]);
});

test("no forecast data is left in browser storage", async ({ page }) => {
  await page.goto(`/?as_of=${SPIKE}`);
  await expect(page.getByRole("button", { name: "Review situation" })).toBeVisible();
  const stored = await page.evaluate(() => JSON.stringify({ ...window.localStorage, ...window.sessionStorage }));
  expect(stored).not.toContain("spot");
  expect(stored).not.toContain("p50");
});
