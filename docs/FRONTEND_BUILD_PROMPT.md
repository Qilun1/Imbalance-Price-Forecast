# Energy Trading Dashboard — Frontend Build Brief

You are a senior design engineer building a production-grade energy trading frontend. Treat this as a **systems task, not a styling task**: every visual value comes from tokens, every component has every state, every number is formatted by one tested formatter, and nothing ships without being seen in a browser and checked against the rules below. Do not improvise visual decisions. When something is not covered here, pick the closest existing rule, apply it, and log the decision in `docs/ui-decisions.md`.

**Scope of this brief:** *what* to show and the market/domain rules come from the backend and your existing context. This brief governs *how* the frontend is built, looks and behaves.

---

## 0. Sources of truth (in priority order)

When two sources conflict, the higher one wins.

1. **The backend and your domain context** — existing API routes, WebSocket messages, schemas/OpenAPI, shared types, and the market rules you already know. Derive every screen, field and domain behavior from them. Never invent endpoints or fields. If something the UI needs is missing, build it behind a typed mock adapter (see §6) and list it in the final report.
2. **This brief** — especially the dashboard overrides in §3.
3. **`DESIGN.md`** in the project root (Oura-inspired system) — colors, fonts, radii, surface treatment, component character, Do's and Don'ts.
4. **Installed skills** — check which are installed before starting and use every relevant one:
   - `make-interfaces-feel-better` — polish review (run in §10).
   - `vercel-react-best-practices`, `web-design-guidelines`, `vercel-composition-patterns` — if installed, follow them for React/Next.js structure and review.
   - `agent-browser` — if installed, use it for the screenshot loop in §10; otherwise use Playwright.
   - `find-skills` may be used to *suggest* further skills, but do not install anything without asking me.
5. **Library defaults** — lowest priority. shadcn/Radix defaults are a starting structure, never the final look.

Ignore any generic "Linear/Mercury dark" style advice. `DESIGN.md` is the visual system.

---

## 1. Operating mode

- Work in the phases below. **Stop after Phase 1 and wait for my go-ahead** before writing UI code.
- Keep a running `docs/ui-decisions.md`: every token you add, every gap you filled, every library you added and why.
- No raw hex, px font sizes, or ad-hoc radii/shadows in component code. Tokens only.
- TypeScript strict. No `any`. No `// @ts-ignore`.
- Don't ask me questions you can answer from the repo. Ask only when a wrong guess would be expensive to undo.

---

## 2. Stack (use exactly this; check `package.json` and use installed versions, never downgrade)

| Concern | Library | Rule |
|---|---|---|
| Framework | Next.js App Router + TypeScript | Server Components for the shell and static data; Client Components only for live/interactive panels. |
| Styling | Tailwind CSS (v4, CSS-first `@theme`) | Tokens defined once as CSS variables, exposed through `@theme`. |
| Primitives | shadcn/ui (Radix underneath) | Add components via the shadcn CLI only as needed, then restyle each one to tokens. Never hand-roll a dropdown, dialog, popover, tooltip, tabs, select or command menu. |
| Motion | Motion (`motion` package, import from `motion/react`) | Only for spatial/layout motion — see §8. |
| Icons | Lucide React | 16px in dense UI, 20px in nav; stroke width consistent app-wide (1.5). |
| Server state | TanStack Query | All REST data. No `useEffect` fetching. |
| Grids | TanStack Table + TanStack Virtual | All tables. Virtualize above ~100 rows. |
| Time-series charts | TradingView Lightweight Charts | Price curves, candles, volume, intraday series. Dynamically imported, client-only. |
| Other charts | shadcn Chart (Recharts) | Non-time-series only (e.g. exposure as bars). |
| Forms | react-hook-form + zod (via shadcn Form) | Order entry and all inputs. |
| Command menu | shadcn Command (cmdk) | ⌘K / Ctrl+K. |
| Toasts | sonner (via shadcn) | Order responses, connection events. |
| Resizable layout | shadcn Resizable | Panel layout on the main trading screen; persist sizes per user. |
| Dates/time zones | date-fns + `@date-fns/tz` | All date/time handling goes through one module. |
| Client UI state | URL search params for shareable state (market, instrument, date); a small store only for ephemeral UI state if needed. |

Any library not on this list needs a one-line justification in `docs/ui-decisions.md`.

---

## 3. Dashboard overrides to DESIGN.md

`DESIGN.md` describes an airy marketing site. Keep its **palette, fonts, surface character, pill buttons, hairlines and restraint**. Override the following for a dense trading tool:

- **Density over silence.** Panel gaps 12–16px, panel padding 16px, table row height 32px (compact) / 40px (comfortable, user toggle). No hero, no full-bleed photography, no large section gaps.
- **Type scale (dense):** 12 / 13 / 14 / 16 / 20 / 24 / 32px. Body and tables 13–14px Inter. The serif (Fraunces) appears **only** for the page title and headline KPI values at ≥24px.
- **Numbers:** `font-variant-numeric: tabular-nums` on every number. Right-align all numeric columns. IDs and raw timestamps may use a mono face (add one, e.g. JetBrains Mono, via `next/font`).
- **Radii:** panels 12px, inputs 8–12px, inner elements follow the concentric rule (outer radius = inner radius + padding). Buttons, tabs, chips stay fully rounded per DESIGN.md.
- **Surfaces:** cream canvas as the app background; panels are white surface with a 1px hairline border, no shadow. Soft warm shadows only on overlays (popovers, dialogs, drawers, toasts). Ink band (near-black) only for the sidebar if it helps — decide once and log it.
- **Action blue** = the single primary trade action (Submit order) per view. Not for links, selected rows, chart lines or status.
- **Earth-tone ramps** (gold, clay, olive/sage) become chart series colors and band accents — never buttons.
- **Color is never the only signal** for direction or status — always pair it with a sign, label or icon.

### Semantic tokens to add (log each with its contrast ratio)

- `--color-up`, `--color-down` (+ `-bg` variants for flashes/badges): muted green and red that fit the earth palette and reach **≥4.5:1 on canvas and on white surface**.
- `--color-buy`, `--color-sell`: may alias up/down, but Buy/Sell must also differ by label and icon.
- `--color-warning`, `--color-info`, `--color-focus` (stone, 2px).
- `--color-chart-grid`, `--color-chart-axis`, `--color-chart-crosshair`, and an ordered series palette of 6 drawn from the earth ramps.

Write a small script that checks every text/background token pair for WCAG contrast and fails the build if one is below AA.

---

## 4. Phase 1 — Discovery & plan (no UI code)

Inspect the repo and produce `docs/frontend-plan.md` containing:

1. **Screen inventory** — every route, its purpose, and its panels, derived from what the backend supports.
2. **Data contract map** — one row per panel: endpoint or stream → TypeScript type → refresh strategy (static / poll interval / WebSocket).
3. **Component inventory** — primitives (from shadcn, restyled) and domain components (e.g. `PriceCell`, `KpiCard`, `OrderTicket`, `OrderBook`, `PositionsTable`, `TradeBlotter`, `ConnectionStatus`, `MarketSelector` — adjust to the plan).
4. **State matrix** — for every domain component: default, hover, active/pressed, focus-visible, disabled, loading, empty, error. Mark which apply.
5. **Assumptions & gaps** — anything missing from the backend, with the mock you'll build for it.

Then stop and wait for me.

---

## 5. Phase 2 — Foundation

1. **Tokens:** read `DESIGN.md` including its YAML front matter; map every token to CSS variables in one tokens file, expose via `@theme`, add the semantic tokens from §3. Run the contrast script.
2. **Fonts:** `next/font/google` — Fraunces (display, high optical size, weight 300) and Inter (everything else), plus a mono. `display: swap`, subsets limited, no layout shift.
3. **Formatters (`lib/format`) with unit tests:** every number, date and time on screen goes through this one module. Never round or format inside components.
4. **Primitives:** install and restyle Button (primary, secondary/stone, outline, ghost, icon), Input, Select, Tabs (pill), Tooltip, Popover, Dialog, Sheet, DropdownMenu, Command, Table chrome, Badge, Skeleton, Toast, Resizable, Switch, ToggleGroup. Build a hidden `/dev/ui` page showing every primitive in every state.

---

## 6. Phase 3 — Data & real-time layer

- **Typed API client** generated from or bound to the backend's types. One module per domain.
- **Mock adapter** implementing the same interfaces, switched by an env variable, with realistic data covering the edge cases you know from the domain, plus errors and disconnects. Mock data never lives in components.
- **WebSocket client:** reconnect with exponential backoff + jitter, heartbeat, resubscribe on reconnect, sequence-gap detection → refetch snapshot.
- **Update batching:** buffer incoming ticks and flush once per animation frame. Subscribe per row/cell so a tick re-renders only what changed — never the whole table.
- **Connection status** always visible in the top bar (Live / Reconnecting / Offline), with a toast on change.

---

## 7. Phase 4 — Screens & layout

- **App shell:** collapsible sidebar (240px ↔ 64px icon rail, state persisted), top bar with market selector, date picker, market clock, connection status, user menu, ⌘K trigger.
- **Trading screen:** resizable panel layout — chart (largest), order book/depth, order ticket, my orders, trade blotter (adjust to the plan). Persist panel sizes. Keyboard focus moves between panels with a documented shortcut.
- **Overview:** KPI row using `KpiCard` (serif value ≥24px, sans label, signed delta), followed by the panels defined in the plan.
- **Order ticket:** fields, limits and summary as defined by the backend and your domain context. Buy/Sell toggle distinguished by label + icon + color. zod validation with inline errors. Confirmation dialog above a configurable threshold. Enter submits only when focus is inside the ticket; Esc clears/cancels. Disable double-submit.
- **Cancel all:** present, guarded by a confirmation dialog stating exactly what will be cancelled.
- **Tables:** sticky header, sortable, column resize, compact/comfortable density, truncation with tooltip for long text, empty state with a one-line explanation and next action, skeleton rows that match final row height.
- **Responsive:** primary target ≥1280px; tested at 1280, 1440, 1920. At 768px the layout stacks and remains usable. Below 768px: read-only summary, no order entry.

---

## 8. Motion & interaction rules

- **CSS transitions** for hover, press, focus, color and opacity: 120–180ms, ease-out. Only animate `color`, `background-color`, `opacity`, `transform`. Never `width`, `height`, `top/left`, or `box-shadow`.
- **Press feedback:** `scale(0.97)` on `:active` for buttons; none on table rows.
- **Hover styles** only inside `@media (hover: hover)`.
- **Motion springs** only for spatial movement: popover/sheet/drawer entrance, layout changes, the active-tab indicator (`layoutId`), panel collapse. Use a fast, non-bouncy spring (e.g. `{ type: "spring", stiffness: 500, damping: 40 }`). Exit animations are shorter and softer than enters.
- **Live data is never animated into place.** Prices and quantities change instantly and exactly. No count-up effects. The only tick feedback is a background flash (`--color-up-bg` / `--color-down-bg`) fading over ~400ms on the changed cell, with no layout shift.
- **`prefers-reduced-motion`:** remove all movement and the flash; show a static up/down arrow instead.
- **Keyboard:** everything reachable by keyboard; ⌘K command menu for navigation and actions (switch market, jump to screen, new order, cancel all with confirm); `?` opens a shortcuts dialog. Shortcuts never fire while typing in an input.
- **Focus:** visible `:focus-visible` ring (2px `--color-focus`, 2px offset) on every interactive element. Radix handles dialog focus trapping — don't break it.

---

## 9. Quality budgets

- **Performance:** INP < 200ms, CLS < 0.05, no dropped frames with 50 ticks/s on the trading screen (verify with the mock). Charts and heavy panels dynamically imported. No layout shift when streams connect or data loads.
- **Accessibility:** WCAG 2.2 AA. Text contrast ≥4.5:1, UI ≥3:1. Real table semantics. `aria-live="polite"` for order responses and connection changes — **not** for price ticks. Touch targets ≥44×44px on touch devices, ≥32px in dense desktop UI with expanded hit areas.
- **Code:** components in `components/ui` (restyled primitives) and `components/trading` (domain); `lib/format`, `lib/api`, `lib/realtime`, `styles/tokens`. No inline hex, no magic numbers, no `any`.

---

## 10. Phase 5 — Verification loop (do this for every screen before calling it done)

1. Run the dev server with the mock adapter.
2. Screenshot each screen at 1280, 1440, 1920 and 768px, in loading, populated, empty and error states (use `agent-browser` if installed, otherwise Playwright).
3. Review screenshots against `DESIGN.md` Do's and Don'ts and §3 and §8 of this brief. Fix every violation.
4. Run `/make-interfaces-feel-better full <screen name>` and apply its fixes where they don't conflict with higher-priority sources (§0).
5. If installed, review against `vercel-react-best-practices` and `web-design-guidelines`.
6. Run: typecheck, lint, unit tests for formatters, contrast script, axe accessibility checks, and a Playwright smoke test of the full order flow from entry to server response against the mock.

---

## 11. Definition of done

- [ ] Every screen in the plan built, using only tokens.
- [ ] Every domain component implements every applicable state from the state matrix.
- [ ] All numbers, dates and times go through `lib/format`, with tests.
- [ ] Live panels batch updates and survive disconnect/reconnect.
- [ ] Contrast script, typecheck, lint, tests, axe and the order-flow smoke test all pass.
- [ ] Screenshots reviewed at all breakpoints; `make-interfaces-feel-better` pass applied.
- [ ] `docs/frontend-plan.md` and `docs/ui-decisions.md` up to date.

## 12. Final report

Finish with: what was built (by screen), token gaps filled and how, libraries added and why, backend gaps still mocked, known limitations, and the screenshots for each screen at 1440px.
