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
| `--color-warning` | `#7a5a0a` | 5.68 | 6.37 | On `#fde9a0`: 5.26 |
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
  High and low price risk gave way to the highest and lowest P50 in the next 10 hours, with their times.
  Hindsight keeps its cards. On wide screens the strip sits above the chart in the left column, matching its
  edges, so the situations run full height on the right. Its columns follow its own width (container query),
  all in one row from 576 px. The chart keeps its time range on resize (`lockVisibleTimeRangeOnResize`), as the narrower column
  otherwise cut off the forecast's end.
- **Imbalance price and forecast chart scrolls through history**, team decision, 7 Nov, after Nordnet's
  period row. It loads every row usable at the viewing time since the data starts (31 May), the same request
  as the price history table. A row under the chart (1 day, 3 days, 1 week, 1 month, 3 months, All; the
  buttons share the box's full width, `Choice fill`) sets how much history is in view; drag, a sideways swipe or the wheel (zoom) reaches the rest. It always shows
  quarter-hours: a 15 min / 1 hour / 2 hours density menu was tried and removed the same day. Axis ticks
  take the date from the chart's own day-change marks, not exact midnight.
- **The chart header stays one row** (`PanelHeader oneRow`): the note never changes and shortens with an
  ellipsis when space runs out, so "Show what happened" keeps its place. Its label's hover text says that
  what it shows was not known at the forecast time.
- **Spot is a line in the imbalance price and forecast chart**, team decision, 7 Nov: Nord Pool spot as a
  2 px `--color-chart-spot` `#7c3aed` line (5.7:1 on white; the muted `--color-series-5` read too light),
  under the imbalance lines, past and the day-ahead prices published for the
  forecast hours, with "Spot" in the readout. Tried first as a separate chart below the fold, then as a
  second chart in the same box; the team wanted one chart.
- **Price history table sits in the "What to check now" box**, above the situations (swapped from under
  them the same day), team decision, 7 Nov.
  Per period (1 day, 1 week, 1 month, 3 months, all data): spot high and low, imbalance high and low, over
  quarter-hours before the viewing time, in whole euros; hovering a price gives its exact value and time.
  The four price columns are equal and centred, so the Spot and Imbalance group names, each underlined,
  sit midway over their High and Low. The situations scroll below it. To fit it, the default split moved
  from 72/28 to 66/34 (storage id `now-across-v3`), the chart note dropped "times in UTC", and the key
  figures hide their "/MWh" suffix when the strip is under 672 px so they still fit in one row. A spot
  change % column was tried and removed the same day.
- **Hindsight follows the Now layout**, team decision, 7 Nov. Left (66 %): the diagnostic scores as the
  same quiet strip as the key figures (`StatStrip`, short labels with the full metric name on hover, "53%
  better" against the baseline, said once in the strip's title), then Forecast vs actual with the Now chart's
  series, names and colours: Actual (ink with a fade), Spot (`--color-chart-spot`, from `/api/actuals` for
  the same window), Forecast (gold) and Prediction interval (band); the dashed baseline line was dropped as too
  busy, the baseline lives on in the strip. Previous day / week / month is a full-width row under it. Right (34 %, resizable): Situations raised as a full-height box, each situation
  a two-line item (level, title, outcome; first raised, window, updates), virtualised past 100, with the
  official validation scores at its foot. The box header says only how many were raised; the judged count
  and the score.py source note were removed, team decision. The six-column log table needed about 920 px and did not fit a
  side box. The screen title is a screen-reader-only h1, as the sidebar names the screen.
- **Screen links read the address when used** (`useScreenHref`), not the last render: pressing `2` right
  after Shift+← carried the old time while the Now screen was still re-rendering its month of history.
- **Softer box edges**, team decision, 7 Nov: `--color-hairline-soft` `#ece7df` on panels, KPI cards and the
  strip, and unselected situation cards. Decorative, so no contrast minimum; tables and inputs keep theirs.
- **The Next 10 hours table has one row height**, team decision, 7 Nov: 40 px (`--spacing-row-comfortable`).
  The compact / comfortable toggle in the box header and its saved setting were removed, as was the 32 px
  token. This drops the prompt's density toggle. Sorting and column resizing stay.
- **Balancing direction is back under the price chart**, team decision, 7 Nov, reversing the one plain pane
  above. A separate Balancing & Risk screen, then a price risk pane under the chart, were tried and removed
  the same day; risk stays in the situations and the Next 10 h table. Direction is a lower pane of the Now
  chart, not a box of its own, so the Forecast line, the selected situation's shading, the crosshair,
  dragging and the History row hold for both panes. The price pane is twice its height. After the Forecast
  line it shows the forecast's chances; before it a pale full-height block is what happened. Changes from
  the pane first removed: up and down are drawn separately, not as their difference, so the axis reads the
  same numbers as the Next 10 h table, and the axis shows whole percent.
- **What happened is a solid bar from the middle line**, team decision, 7 Nov. Pale full-height blocks
  behind the chances could not be told from the forecast, and bars in lanes of their own outside the 100 %
  lines read as detached, so the bars are back at the middle line, in the up and down colours at full
  strength. "Show what happened" carries the bars past the Forecast line. The chances are see-through
  (35 %), team decision, 7 Nov, so a bar shows through them in full; an opaque tint in front hid the bars.
  Over a bar of its own colour a see-through fill cannot be seen, so there the chance's 2 px edge turns
  white (per-point line colours) and still marks it: solid is what happened, pale or a white step is the
  forecast. They are `Blocks`, not a series: Lightweight Charts joins a line across empty
  rows, which would draw a bar over the quarter-hours not yet published at the forecast time.
- **The Forecast line marks where the prediction starts**, team decision, 7 Nov: 2 px `--color-ink`, was a
  faint grey hairline, with a dark tag "Forecast from 21:00 →" at the top of the price pane. In the lower pane
  the line starts below the heading strip, so it never crosses the figures there.
- **Hindsight has the same direction pane**, team decision, 7 Nov: `DirectionPane`, shared with the Now
  chart, so bars, chances, heading row and crosshair behave the same. `HindsightPoint` gained `p_up` and
  `p_down`, from the same forecast rows as its P50, so they carry the same `as_of` limit. The direction that
  happened comes from the usable actuals, as the spot line does.
- **Forecast vs actual shows the forecast made 1 hour ahead**, team decision, 7 Nov: the 1 h, 4 h and 10 h
  ahead buttons were removed. The API keeps `lead_hours`, and the chart's description still names the lead.
- **The score strip's title names the period**, team decision, 7 Nov: "Diagnostic for Previous Day", "Previous
  Week" or "Previous Month", which still labels the figures as diagnostics (rule 5). The title no longer
  says "vs baseline", so each figure does: "34% better than baseline".
- **The chart note reads "shaded band (prediction interval 80%)"**, team decision, 7 Nov, on Now and Hindsight.
- **The direction pane's heading row works like the readout**, team decision, 7 Nov: "Balancing direction",
  then Up and Down with pale swatches like the chances, then Happened with a solid swatch like the bars and
  "02:30 Down, decided at −€6.1". Up and Down follow the crosshair, as the band does; Happened names its own
  time, as away from known quarter-hours it stays on the latest one. The price is the imbalance price, since
  the direction decides how that price is calculated, not the mFRR marginal price, which the API does not
  serve. It is written, not drawn, as the pane's axis is percent and a price line would have no scale there.
  The strip is 24 % of the pane (was 14 %) so it no longer sits tight between the graphs, and the row takes
  more lines only when the pane is too narrow for one. A canvas cannot be read aloud, so the band holds the
  same words out of sight (`data-field=direction`).
- **The chart readout is a filled band**, team decision, 7 Nov, as the names and numbers above the chart
  were hard to see: `Readout` (`bg-fill`, the highlighted panel title's look), ink text, semibold values,
  larger swatches. It holds one row, the prices: time, actual, spot, forecast and prediction interval, on
  Now and Hindsight alike. The text follows the band's inner width (container query): 11 px with 4 px gaps
  from 38rem, which is the default split at 1280 px, 12 px from 43rem, 13 px from 47rem, 14 px from 50rem.
  Each step starts where the row with realistic values was measured to fit, and value widths are in em so
  they shrink with it. 11 px is the one size below the type scale, the cost of one row at 1280 px; a rare
  four-digit negative price there reaches into the band's padding. Below 38rem, a phone or a panel dragged
  narrow, it wraps rather than cutting off values. The time is the short "23 Oct 09:00".
- **The readout row spans the band evenly**, team decision, 7 Nov: on one line its items share out the room
  left over (`justify-between`), and the time keeps half an em after it, as it fills its whole width while the
  values keep room beside theirs. The prediction interval keeps 8em, was 8.4em, to pay for that at 1280 px, and Actual 3em, was 3.6em, as it reads "–" through the forecast hours and the wider room left a gap after it.
- **The Now key figures show their time in the chart**, team decision, 7 Nov. Each figure is a toggle button
  (`aria-pressed`) laid over the figure: pressed, the chart shades its quarter-hours in grey and puts the
  crosshair and readout on the first. Next hour price and Direction next hour shade the whole next hour,
  Highest and Lowest price their one quarter-hour. A figure takes over the shading from the selected
  situation, picking a situation lets go of the figure, and pressing the figure again lets go. The pick is
  the figure, not its times, so stepping the viewing time follows the new forecast's highest or lowest.
  Pressing a figure also sets the History row back to 1 day, team decision, 7 Nov, where its quarter-hours
  are easy to see; letting go keeps whatever span is chosen.
- **The forecast series is named "Forecast (Imbalance)"** in the readouts of Now and Hindsight, team
  decision, 7 Nov, so it reads as the imbalance price forecast beside Spot. The tag on the Forecast line keeps
  "Forecast from 21:00 →", as it marks where the whole forecast starts, the direction pane's included.
- **Largest revision left the key figures**, team decision, 7 Nov. Forecast changes stay on the Next 10 h
  screen and in the situations.
- **"Prediction interval (80%)" replaces "likely range"**, team decision, 7 Nov, everywhere the P10–P90 band
  is named: the chart notes and readouts of Now and Hindsight and the Next hour figure, which puts the
  name and the numbers on two lines, as one line cut off the numbers. "Confidence interval" was used
  briefly; it is the wrong term for the spread of an outcome rather than of an estimate.
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
- **Situation levels are red and yellow**, team decision, 7 Nov. Review is `--color-error-text` on
  `--color-error-bg`, Watch is `--color-warning` on `--color-warning-bg`, which moved from `#f6ecd2` to
  `#fde9a0` because the old value read as tan on the cream theme. The `--color-up` red is not used: it means
  a rising price. Each badge keeps its icon and word, so colour is never the only signal. The chart's shade
  for the selected situation follows the level, as a see-through tint: an opaque fill hid the prediction interval
  drawn under it.
- **Highlighted titles**, team decision, 7 Nov. "What to check now", "Situations raised" and "Official
  validation scores" use `PanelHeader highlight`: 16 px ink on a `--color-fill` band (14.76). The band is
  neutral because red and yellow mark situation levels. Other panel titles stay quiet.
- **Hindsight's caption is gone**, team decision, 7 Nov. The line under the scores was removed. Its job moved
  to the strip's visible title, "Diagnostic scores vs baseline", which keeps the figures labelled as
  diagnostics beside the official ones (rule 5). The API still returns the note.
- **P10–P90 coverage left the score strip**, team decision, 7 Nov. It stays as a row in the official table.
  `StatStrip` now shares its row equally among any number of figures, so four fill Hindsight's strip and the
  Now screen keeps four.
- **Score names**, team decision, 7 Nov. "Exceptional prices" and "Direction" became "Spike error" and
  "Direction error", in the strip and the official table, because the old names read as topics, not scores.
  The full names keep "(Brier)". Brier scores have no unit, so these two show plain numbers.
- **Hindsight's chart shows only what happened**, team decision, 7 Nov. The imbalance price arrives about an
  hour late, so the last four quarter-hours before the viewing time had a forecast and no actual, which read
  as a forecast into the future. Every line now ends at the last known actual (`upToLastActual`). Gaps earlier
  in the period stay gaps, and the API is unchanged.
- **API screen, essentials only**, team decision, 8 Nov, for the brief's Level 2 "plus an API from which this
  information can be retrieved for display". Sidebar "API", key `4`, route `/api-guide` (`/api` itself is
  what `next.config.ts` sends to the backend). It assumes the model's forecasts are loaded and the API runs in
  real mode (`docs/LIVE_DEPLOYMENT.md`, step 4), so it holds one box, Pull the data: four endpoints, one
  PowerShell example, `as_of` and the spot rule in one line each. The interactive docs button holds the rest.
  The title and the box form one column, at most 56rem wide, centred in the page and 2rem lower than the other
  screens' content, team decision.
  Cut down the same night, team decisions: a first version with a status strip, long steps, every endpoint,
  examples in three languages, the live JSON answer and a rules box was too much, and a second one with a
  status line and start-up commands still showed more than the instructions. The example names the forecast
  fields it prints, so it never prints the spot price (rule 6). No new tokens or libraries.

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
