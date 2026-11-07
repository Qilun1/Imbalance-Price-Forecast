# UI decisions

Running log required by `FRONTEND_BUILD_PROMPT.md` §1: every token added, gap filled and library added,
and why. The plan is in [frontend-plan.md](frontend-plan.md).

## Tokens

### Contrast of `DESIGN.md` colours

Needed: 4.5:1 for text, 3:1 for UI and chart marks.

| Token | Hex | On canvas | On white | Decision |
|---|---|---|---|---|
| ink | `#1c1b1a` | 15.32 | 17.20 | Primary text |
| stone | `#4a4741` | 8.24 | 9.26 | Secondary text, focus ring on light surfaces |
| ash | `#838280` | **3.42** | **3.84** | Fails as text. Replaced by `--color-text-muted` |
| mute | `#a8a5a0` | **2.19** | **2.45** | Fails on light. Allowed only on the ink sidebar (7.15) |
| primary | `#2a72de` | 4.10 | 4.61 | Fill only, white text on it is 4.61. Never text on canvas |
| error | `#e33a22` | **3.82** | **4.29** | Fails as text. Replaced by `--color-error-text` |
| gold | `#af751b` | 3.47 | 3.90 | Chart marks only |

### Semantic tokens added

| Token | Hex | On canvas | On white | Note |
|---|---|---|---|---|
| `--color-text-muted` | `#6a6762` | 5.01 | 5.63 | Replaces ash |
| `--color-up` | `#a8391f` | 5.72 | 6.42 | Up-regulation, high price |
| `--color-down` | `#007a5e` | 4.74 | 5.32 | Down-regulation, low price |
| `--color-up-bg` | `#f6e3dc` | | | `--color-up` on it: 5.18 |
| `--color-down-bg` | `#e0f1ea` | | | `--color-down` on it: 4.55 |
| `--color-warning` | `#7a5a0a` | 5.68 | 6.37 | On `#f6ecd2`: 5.42 |
| `--color-info` | `#4a5a6a` | 6.31 | 7.09 | On `#e6e9ec`: 5.82 |
| `--color-error-text` | `#b82a14` | 5.53 | 6.21 | On `#fbe6e1`: 5.18 |
| `--color-focus` | stone | 8.24 | 9.26 | Light surfaces |
| `--color-focus-on-dark` | canvas | | | Stone is only 1.90 on the sidebar. Canvas is 15.62 |
| `--color-fill` | `#f3ede2` | | | Warm hover and selected fill. Every text colour on it passes |
| `--color-control-border` | `#8d8982` | ≥3 | ≥3 | Input edges. Hairline is too faint to show where a field is |
| `--color-action-hover`, `--color-stone-hover`, `--color-sidebar-hover` | | | | Hover states. White text on each passes |
| `--color-error-bg`, `--color-warning-bg`, `--color-info-bg` | | | | Badge backgrounds. Their text passes |
| `--color-chart-band`, `--color-chart-zone` | | | | P10-P90 fan and spot ± 50 zone, used with transparency |

`scripts/check-contrast.mjs` checks 62 pairs on every build and fails it below AA.

**Radii.** Tailwind names map to `rounded-sm` 6, `rounded-md` 8 (inputs), `rounded-lg` 12 (panels), `rounded-xl`
16 and `rounded-2xl` 24 (dialogs). A menu of 12 with 4 padding holds items of 8, which is concentric. A card
16 px inside a panel is a separate surface, as the polish skill allows, so its radius is chosen on its own.

`--color-chart-grid` is hairline, `--color-chart-axis` is `--color-text-muted`, and
`--color-chart-crosshair` is stone. `--color-buy` and `--color-sell` are not added, because there is no
order entry. Short and Long use `--color-down` and `--color-up`, with label and icon.

### Up and down colours

A muted red with an olive green fails for red-green colour blindness: ΔE was 1.8 to 5.3 against a target
of 8. Shifting the green towards teal fixes it. `#a8391f` with `#007a5e` passes all five palette checks,
with ΔE 8.4 (deutan), and meets 4.5:1 on canvas and on white.

**Why red for up.** Up-regulation means scarcity and a price above spot, so it reads as "hot". A green "up"
would suggest good news, but a high price is only good or bad depending on the position. To be confirmed
with Turku Energia. Colour is never the only signal: direction also has a sign, label or position.

### Chart series palette

The raw earth ramps fail as a categorical palette: four of six are below the chroma floor, and worst
adjacent ΔE is 5.1. So the ramps are the starting point, and these are tuned to pass.

| Slot | Hex | Origin |
|---|---|---|
| 1 | `#af751b` | gold |
| 2 | `#007a5e` | forest and olive, moved towards teal |
| 3 | `#a8391f` | clay, more saturated |
| 4 | `#7f8f24` | olive, more saturated |
| 5 | `#6d5a9a` | not an earth tone. No earth tone passed here |
| 6 | `#c07c2e` | ochre |

All checks pass on white and on canvas (`dataviz` validator). No chart needs more than four series, so
slots 5 and 6 are a reserve.

**Main chart reading.** P50 is the emphasised series in gold, the band is a tint of the same hue with thin
gold edges, the actual price is ink, spot is stone, and the spot ± 50 zone is a faint fill. Model against
baseline uses gold against a neutral, not slots 2 and 3, because those colours mean up and down.

## Conflicts resolved

The prompt ranks above `DESIGN.md`, which ranks above skills.

| Topic | Lower source says | Applied | Why |
|---|---|---|---|
| Press scale | `make-interfaces-feel-better`: 0.96 | 0.97 | Prompt §8 |
| Card edges | Same skill: shadows instead of borders | 1 px hairline, no shadow on panels | Prompt §3 |
| Hit area | Same skill: 40 px in dense UI | 32 px with expanded hit areas, 44 px on touch | Prompt §9 |
| Hover shadow | Same skill: transition `box-shadow` | Not animated | Prompt §8 |
| KPI numerals | `dataviz`: sans, no `tabular-nums` on large values | Fraunces at ≥24 px with `tabular-nums` | Prompt §3. Check in Phase 2 that Fraunces has tabular figures |
| Data fetching | `vercel-react-best-practices`: SWR | TanStack Query | Prompt §2 |
| Text input fill | `DESIGN.md`: stone fill | White input with hairline border | Prompt §3 surfaces, and it suits dense forms |
| Action blue | Prompt: Submit order | "Review situation" on Now, "Exposure check" on Next 10 h, none on Hindsight | No orders exist. See plan §0. A browser test checks there is never more than one |
| Display serif | Prompt: Fraunces at high optical size, weight 300 | Optical size 48, weight 340, at 32 px, with lining figures | At 24 px and full optical size the hairlines made KPI numbers hard to read at a glance. Legibility for the expert outranks the look |
| Selected pill | `DESIGN.md`: 2 px silver border | Stone fill with white text | Silver is 1.46:1, below the prompt's 3:1 for UI |
| Heading case | Web Interface Guidelines: Title Case | Sentence case | The prompt's own examples and Vercel's writing guidelines use it |
| Time stepping keys | Plan: `[` and `]` | Arrow keys | `[` and `]` need AltGr on a Finnish keyboard |
| Sheet entrance | Prompt: Motion springs for sheets | shadcn's CSS slide, 200 ms ease-out | Short and interruptible already. Motion runs the active-screen pill, where movement says something |
| Chart attribution | Lightweight Charts: a logo on the chart | The notice and link in the Keyboard shortcuts dialog, on every screen | Team decision, 7 Nov: no TradingView text on the chart panels. The logo sat on the data, and the licence still asks for the notice and link on the page |
| Overlay backdrop | shadcn: blur | A plain dim | The expert compares the sheet with the table behind it |
| Connection status | Prompt §6: always visible in the top bar | Not shown. A toast announces a lost or restored connection, and the last data stays on screen | Team decision, 7 Nov. The toast keeps the `aria-live` announcement |

## Layout

- **Sidebar:** ink band `#19191c`. It frames the data without shadows, and it is the only dark surface, so
  it stays clear on a projector.
- **Theme:** light only. `DESIGN.md` has no dark palette.
- **Source folder:** `frontend/src/`, as the repo already has, holding `app`, `components/ui`,
  `components/trading`, `lib/format`, `lib/api`, `lib/realtime` and `styles`.
- **`components/trading` and `lib/realtime`** keep the prompt's names. `lib/realtime` holds the connection
  status, viewing time and replay clock.
- **Chart colours** are read from CSS variables at runtime, because a canvas cannot use Tailwind classes.
- **Forecast chart is one plain pane**, team decision, 7 Nov, after a Nordnet chart showed how much clearer a
  single line reads. It holds the actual price (dark line, soft fade under it), the P50 forecast (gold) and
  the P10–P90 range as a light band, with straight lines, not steps. Gone: the risk and direction panes, the
  spot line, the grey spot ± 50 zone, vertical grid lines, day lines and axis decimals. Only the selected
  situation's window is shaded. Risk stays in the situations and the Next 10 h table, direction also in the
  KPI row.
- **KPI row is one strip**, team decision, 7 Nov, styled after a Nordnet quote line: a muted label, a plain
  semibold number and one line of context, with no card per figure. Prices read in euros, as "€63.9 /MWh".
  High and low price risk gave way to the highest and lowest P50 in the next 10 hours, with their times. The
  largest revision takes the up colour when positive and the down colour when negative. Hindsight keeps its
  cards. On wide screens the strip sits above the chart in the left column, matching its edges, so the
  situations run full height on the right. Its columns follow its own width (container query), five from
  672 px. The chart keeps its time range on resize (`lockVisibleTimeRangeOnResize`), as the narrower column
  otherwise cut off the forecast's end.
- **Imbalance price and forecast chart scrolls through history**, team decision, 7 Nov, after Nordnet's
  period row. It loads every row usable at the viewing time since the data starts (31 May), the same request
  as the price history table. A row under the chart (1 day, 3 days, 1 week, 1 month, 3 months, All; the
  buttons share the box's full width, `Choice fill`) sets how much history is in view; drag, a sideways swipe or the wheel (zoom) reaches the rest. It always shows
  quarter-hours: a 15 min / 1 hour / 2 hours density menu was tried and removed the same day. Axis ticks
  take the date from the chart's own day-change marks, not exact midnight.
- **The chart header stays one row** (`PanelHeader oneRow`): the note never changes and shortens with an
  ellipsis when space runs out, so "Show what happened" keeps its place. With it on, the readout row says
  the black line after "Forecast" was not known then.
- **Spot is a line in the imbalance price and forecast chart**, team decision, 7 Nov: Nord Pool spot as a
  2 px `--color-chart-spot` `#7c3aed` line (5.7:1 on white; the muted `--color-series-5` read too light),
  under the imbalance lines, past and the day-ahead prices published for the
  forecast hours, with "Spot" in the readout. Tried first as a separate chart below the fold, then as a
  second chart in the same box; the team wanted one chart.
- **Price history table sits in the "What to check now" box**, under the situations, team decision, 7 Nov.
  Per period (1 day, 1 week, 1 month, 3 months, all data): spot high and low, imbalance high and low, over
  quarter-hours before the viewing time, in whole euros; hovering a price gives its exact value and time.
  The four price columns are equal and centred, so the Spot and Imbalance group names, each underlined,
  sit midway over their High and Low. The situations scroll above it. To fit it, the default split moved
  from 72/28 to 66/34 (storage id `now-across-v3`), the chart note dropped "times in UTC", and the key
  figures hide their "/MWh" suffix when the strip is under 672 px so five still fit in one row. A spot
  change % column was tried and removed the same day.
- **Hindsight follows the Now layout**, team decision, 7 Nov. Left (66 %): the diagnostic scores as the
  same quiet strip as the key figures (`StatStrip`, short labels with the full metric name on hover, "53%
  better" against the baseline, said once in the caption), then Forecast vs actual with the Now chart's
  series, names and colours: Actual (ink with a fade), Spot (`--color-chart-spot`, from `/api/actuals` for
  the same window), Forecast (gold) and Likely range (band); the dashed baseline line was dropped as too
  busy, the baseline lives on in the strip. Previous day / week / month is a full-width row under it. Right (34 %, resizable): Situations raised as a full-height box, each situation
  a two-line item (level, title, outcome; first raised, window, updates), virtualised past 100, with the
  official validation scores at its foot. The box header says only how many were raised; the judged count
  and the score.py source note were removed, team decision. The six-column log table needed about 920 px and did not fit a
  side box. The screen title is a screen-reader-only h1, as the sidebar names the screen.
- **Screen links read the address when used** (`useScreenHref`), not the last render: pressing `2` right
  after Shift+← carried the old time while the Now screen was still re-rendering its month of history.
- **Softer box edges**, team decision, 7 Nov: `--color-hairline-soft` `#ece7df` on panels, KPI cards and the
  strip, and unselected situation cards. Decorative, so no contrast minimum; tables and inputs keep theirs.
- **Exposure check** moved from a side panel into a sheet. The panel pushed three table columns off screen at
  1440 px, and the quarter-hour table is what the demo must show.
- **Sidebar** drops to the icon rail below 1024 px, so 768 px keeps its width for data.
- **No top bar**, team decision, 7 Nov. The viewing time controls, the forecast stamp, the Ctrl K button and
  the situation timeline under them are gone. The viewing time still lives in the URL (`?as_of=`), and the
  keys still move it: `←` `→` an hour, Shift for a day, `L` latest, `R` replay, Ctrl K the command menu,
  `?` the shortcuts. Phones keep a bar with only the screen links, because the sidebar is hidden there.
- **Past views** carry no notice, team decision, 7 Nov.
- **UTC:** everything that names the viewing time reads UTC, team decision, 7 Nov: the Ctrl K jumps. Page
  content, including tables and chart axes, stays in Helsinki time.
- **Now screen** drops the Main factors and Largest changes panels, team decision, 7 Nov. The forecast chart
  takes their space. Main factors stay in the Next 10 h table and the situation sheet, and the largest
  revision stays in the KPI row.
- **Now screen title** moved into the situations panel, team decision, 7 Nov. The panel header reads "What to
  check now" with the count, in the panel title style, and is the page's `h1`. The large title row is gone.
  On wide screens the forecast chart is on the left and that panel on the right; stacked, it stays first.
- **Hindsight** drops the Error by hours ahead chart, team decision, 7 Nov. Forecast vs actual takes the full
  width. The API still returns the scores by hour ahead.

## Libraries beyond the prompt's list

| Library | Why |
|---|---|
| `openapi-typescript` | Already in the repo. Generates API types from the backend's OpenAPI |
| `react-day-picker` | Used by shadcn Calendar for the viewing date |
| `vitest` | Unit tests for `lib/format` |
| `@playwright/test`, `@axe-core/playwright` | Smoke, screenshot and accessibility checks the prompt asks for. Playwright drives installed Edge |
| `eslint`, `eslint-config-next` | The prompt's lint step |
| `cn`, `radix-ui`, `class-variance-authority`, `tw-animate-css`, `shadcn` | Installed by `shadcn init`. `cn` is shadcn's own MIT package, replacing `clsx` and `tailwind-merge` |

`next-themes` came with the shadcn Sonner wrapper and was removed, because there is no dark mode.
`shadcn` now ships Field in place of Form, so forms use Field with react-hook-form and zod. TanStack Table is
on v9, so tables use `useTable` with explicit features.

## Setup notes

- `shadcn init --base radix --preset nova --no-monorepo`. It needs `next.config` and the `@/*` alias first.
  Without `--base radix` the default is Base UI, which the prompt does not allow.
- `next.config` sets `agentRules: false`. Otherwise `next dev` writes `frontend/AGENTS.md` and re-adds it.
- Turn off Next telemetry once with `npx next telemetry disable`.
