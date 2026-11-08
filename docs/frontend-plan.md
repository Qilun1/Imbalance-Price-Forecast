# Frontend plan

Phase 1 output of `FRONTEND_BUILD_PROMPT.md`, kept up to date as the build went on. **Status: P0, P1 and
two of the P2 items are built.** Section 6 lists what is left. Token values, conflicts and library choices
are logged in [ui-decisions.md](ui-decisions.md).

## What we are building

A decision-support dashboard for a Turku Energia production shift supervisor or electricity trading
specialist. It answers "What should I check now?" and "What is coming in the next 10 hours?", shows how
the forecast performed in hindsight, and lets the viewer move the point of review into the past.

It says "check this situation", never "offer this amount from this plant to this market". Open data
cannot show free capacity, marginal cost, ramp speed, or heat, contract and ownership constraints.

Turku Energia's brief and the backend decide what is shown. `FRONTEND_BUILD_PROMPT.md` decides how it is
built and how it behaves. `DESIGN.md` decides how it looks.

## 0. What changes from the build prompt

The prompt is written for an order-entry trading terminal. Its own §0 ranks the backend and the domain
first, and its §4 and §7 say to adjust components to the plan. So these items change:

| Prompt says | We do | Why |
|---|---|---|
| Order ticket, order book, my orders, trade blotter, positions, Cancel all | Not built | The brief requires no trading, and the backend has no such data |
| Buy/Sell form rules | Kept on `ExposureCheck`: Short/Long with label, icon and colour, zod errors, Enter and Esc | Closest real form. It estimates a cost and places nothing |
| Action blue = Submit order | Blue = "Review situation" on the top situation, at most once per view | The decisive action in this product |
| Market selector, instrument | Not built | One market: Finland |
| Date picker, market clock | `ViewingTimeControl`, in UTC | This is the Level 2 "move the point of review" |
| WebSocket, heartbeat, sequence gaps, 50 ticks/s budget | REST only | Forecasts update hourly and the API has no stream. The prompt forbids inventing endpoints |
| Connection status | A toast when the connection is lost or restored, from polling `/api/meta`. Nothing permanent in the top bar | Team decision, 7 Nov |
| Tick flash | On P50 cells that change when the forecast updates, as in Replay | The nearest case of a value changing while being watched |
| User menu, per-user settings | Not built. Settings stay in this browser | No users or login |
| Mock adapter | The backend's seeded mock mode stays the one source of invented data. The frontend adds a fault wrapper for slow, error and offline states | One source of truth. Rule 0 blocks JSON fixtures |
| Order-flow smoke test | Review-flow smoke test: open a past moment, open a situation, reveal the outcome, run an exposure check | Same purpose, real flow |

Everything else in the prompt stands: the stack, tokens, formatters, states, motion rules, budgets and
the verification loop.

## 1. Screen inventory

### What Turku Energia asks for, and where it is met

| Asked for | Where |
|---|---|
| Forecast price for each quarter-hour, next 10 hours | Forecast chart, Forecast table |
| Uncertainty interval | P10–P90 band, table columns |
| Direction of the balancing need | Direction pane, KPI, table |
| Probability of an exceptionally high and low price | Risk pane, KPIs, table, spot ± 50 zone on the chart |
| Main factors | Drivers panel, situation cards, table |
| When the forecast was made and how fresh the data is | `ForecastStamp`, always in the top bar |
| Surface only the situations that matter | Situations panel, with a designed "nothing to check" state |
| Spike risk rose, regulation expected, forecast changed, signals conflict, expert review | The seven alert kinds shown as situation cards |
| Reasoned suggestion of when to reconsider trading, production plan or capacity | "Worth checking" line on each card, Review sheet |
| What to check now and over the next 10 hours | Now screen |
| Performance over the previous day, week or month | Hindsight screen |
| Move the point of review into the past | Viewing time, global on every screen |
| Insights that give experts new information | [Show what happened](#now), What happened per past situation, Revision trail, Exposure check, Error by hours ahead, Situation timeline, Replay |

### App shell, on every route

- **Sidebar:** 240 px, collapses to a 64 px rail, ink band. Now, Next 10 h, Hindsight.
- **Top bar:** `ViewingTimeControl`, `ForecastStamp`, ⌘K trigger, all in UTC.
- **Situation timeline:** a thin strip under the top bar with one mark per hour of the whole period,
  showing when situations occurred. Click to jump there.

**Viewing time** lives in the URL as `?as_of=<UTC>`. No value means the API's start: with real data the first test forecast (5 Oct 00:00 Helsinki), with mock data the newest one. It carries across
routes and can be shared as a link. Moving it into the past shows only what was known then, and "Back to
latest" appears in the top bar.

### Routes

| Route | Purpose | Panels |
|---|---|---|
| `/` **Now** | What to check now and what is coming | KPI row, Situations, Forecast chart, Drivers, Changes since previous update |
| `/next-10h` **Next 10 h** | Every quarter-hour in detail | Forecast table, Exposure check in a sheet |
| `/hindsight` **Hindsight** | How the forecast performed | Range toggle, Official validation scores, Diagnostic scores, Error by hours ahead, Forecast vs actual, Situation log |
| `/dev/ui` | Hidden. Every primitive in every state | Primitive gallery |

### Now

- **KPI row:** next-hour price with P10–P90, highest high-price risk and when, highest low-price risk and
  when, direction next hour, largest revision since the previous update.
- **Situations (left):** in API order, review first, then soonest. Each card shows severity, kind, window,
  message, "Worth checking", drivers and evidence. Selecting one shades its window on the chart and
  scopes Drivers and Changes to it. "Review situation" opens the Review sheet with the Revision trail.
- **Forecast chart (largest):** three panes on one time axis, each with its own single scale.
  1. Price: last 24 h of actuals, P10–P90 band, P50, spot, spot ± 50 zone, a marker at the forecast time.
  2. Exceptional price risk: high upward, low downward.
  3. Balancing direction: up upward, down downward, realised direction on the history side.
- **Show what happened:** in the past only. Overlays the realised price after the viewing time, clearly
  labelled "Not known at this time". It is off by default. This is what proves usefulness over time.

### Next 10 h

- **Forecast table:** time, spot, P10, P50, P90, spread vs spot, direction, up, down, high risk, low risk,
  change, drivers. 40 rows, so no virtualisation is needed. This is also the accessible twin of the chart.
- **Exposure check:** opens in a sheet, so the table keeps the full width and stays readable behind it.
  The expert enters a hypothetical open position (Short or Long, MW, window). It shows
  the expected cost compared with spot in euros, with a P10–P90 range. Volume is the expert's own input,
  so this stays inside the scope limit. Labelled as an estimate, not a recommendation.

### Hindsight

- **Range:** previous day, week or month, counted back from the viewing time.
- **Official validation scores:** `score.py` results against the baseline. These are the numbers to quote.
- **Diagnostic scores:** the chosen window against the baseline, labelled as a diagnostic (rule 5).
- **Error by hours ahead:** how far ahead to trust the forecast.
- **Forecast vs actual:** for a chosen lead time (1, 4 or 10 h ahead).
- **Situation log:** past situations and whether each one happened, judged only on prices usable at the
  viewing time. Clicking a row jumps to that viewing time. The header gives the running count, for example
  "Of 34 that can be judged, 21 happened".

### Demo path the screens are built for

Calm hour with nothing to check → step forward until a spike risk appears → open the situation, see its
window, drivers and "worth checking" → the 15-minute table → step back, then Show what happened →
Hindsight, week view against the baseline → official validation scores → Exposure check.

## 2. Data contract map

| Screen | Panel | Endpoint | Type | Refresh |
|---|---|---|---|---|
| Shell | Range, periods, spike margin | `GET /api/meta` | `Meta` | Load, then poll every 60 s (also the connection check) |
| Shell | `ForecastStamp` | `GET /api/forecast?as_of=` | `Forecast` | Viewing time |
| Shell | Situation timeline | `GET /api/alerts/history` **(new, G2)** | `AlertHistory` | Load, immutable |
| Now | KPI row | `/api/forecast`, `/api/changes` | `Forecast`, `Changes` | Viewing time |
| Now | Situations | `GET /api/alerts?as_of=` | `Alerts` | Viewing time |
| Now | Forecast chart | `/api/forecast`, `GET /api/actuals?as_of=` | `Forecast`, `Actuals` + spot **(G1)** | Viewing time |
| Now | Show what happened | `/api/actuals?as_of=` is left out on purpose, it is hindsight | `Actuals` | On toggle, immutable |
| Now | Drivers | `/api/forecast`, derived in `lib` | `Forecast` | Viewing time |
| Now | Changes | `GET /api/changes?as_of=` | `Changes` | Viewing time |
| Review sheet | Revision trail | Last 10 `/api/forecast?as_of=` in parallel | `Forecast[]` | On open, immutable |
| Next 10 h | Forecast table | `/api/forecast`, `/api/changes` | `Forecast`, `Changes` | Viewing time |
| Next 10 h | Exposure check | `/api/forecast`, local maths | `Forecast` + spot **(G1)** | On submit |
| Hindsight | Official and diagnostic scores, Error by hours ahead | `GET /api/performance?from=&to=&as_of=` | `Performance` | Range and viewing time |
| Hindsight | Forecast vs actual | `GET /api/hindsight` **(new, G3)** | `Hindsight` | Range, lead time |
| Hindsight | Situation log | `/api/alerts/history` **(new, G2)** | `AlertHistory` | Range |

**Refresh strategies**

- **Latest** (no `as_of`): when the `/api/meta` poll sees a new `last_origin_utc`, the other queries refetch.
- **Past** (`as_of` set): a past answer never changes, so `staleTime` is infinite. The hours either side
  are prefetched, so stepping feels instant.
- **While changing time:** hold the previous render until new data lands, with no skeleton flash.
- **All data** goes through TanStack Query in client components. The shell is a Server Component. The
  browser reaches the API through a Next rewrite of `/api/*`, so there is no CORS setup.

**API errors**

| Status | Meaning | UI |
|---|---|---|
| 404 | Viewing time outside the data | Panel error with "Back to latest" |
| 422 | Time without a zone | Should never happen: `lib/format` always sends `Z` |
| Network | API down | A toast, and the last data stays visible |

## 3. Component inventory

**Primitives** (`components/ui`, added with the shadcn CLI, restyled to tokens): Button (primary, stone,
outline, ghost, icon), Input, Select, Tabs (pill), Tooltip, Popover, Dialog, Sheet, DropdownMenu, Command,
Table, Badge, Skeleton, Sonner, Resizable, Switch, ToggleGroup, plus Calendar and Form, which the viewing
time and Exposure check need.

**Domain** (`components/trading`):

| Component | Job |
|---|---|
| `AppShell`, `Sidebar`, `TopBar` | Layout, collapse state, panel focus |
| `ViewingTimeControl` | Date and hour picker, step ±1 h and ±1 day, Back to latest |
| `ForecastStamp` | Forecast time, latest data time, data age, spot known until |
| `KpiCard` | Serif value, sans label, signed delta |
| `PriceCell`, `DirectionLabel` | A number with an optional change flash, and direction as arrow, word and colour |
| `SituationList`, `SituationCard` | Ranked situations, selection, "nothing to check" state |
| `SituationSheet` | Full reasoning, evidence, Revision trail, copy as a shift note |
| `RevisionTrail` | How P50 and risk for a window moved over the last 10 updates |
| `ForecastChart` | Three panes, band and window primitives, crosshair readout |
| `DriverList` | Ranked drivers for a window |
| `ChangesPanel` | What moved since the previous update |
| `ForecastTable` | TanStack Table: sort, resize, density, truncation with tooltip |
| `ExposureCheck` | react-hook-form and zod, Short/Long, result with range |
| `ScoreCard`, `ScoreTable` | Scores against the baseline, official and diagnostic kept apart |
| `HorizonChart` | Error by hours ahead (Recharts, not a time series) |
| `HindsightChart` | Forecast vs actual (Lightweight Charts) |
| `SituationTimeline`, `SituationLog` | Whole-period strip and past-situation table |
| `CommandMenu`, `ShortcutsDialog` | ⌘K and `?` |

**Keyboard:** `←` and `→` step one hour, `Shift` with them one day, `L` back to latest, `R` replay or pause,
`1` `2` `3` switch screens, `F6` moves focus between panels. None of these fire while typing. The arrows
replace the planned `[` and `]`, which need AltGr on a Finnish keyboard.

## 4. State matrix

● applies, – does not.

| Component | Default | Hover | Active | Focus | Disabled | Loading | Empty | Error |
|---|---|---|---|---|---|---|---|---|
| `Sidebar` | ● | ● | ● | ● | – | – | – | – |
| `ViewingTimeControl` | ● | ● | ● | ● | ● range ends | ● | – | ● out of range |
| `ForecastStamp` | ● | – | – | ● | – | ● | ● no cutoff | ● stale data |
| `KpiCard` | ● | – | – | – | – | ● | ● | ● |
| `PriceCell`, `DirectionLabel` | ● | – | – | – | – | ● | ● null | – |
| `SituationList` | ● | – | – | – | – | ● | ● nothing to check | ● |
| `SituationCard` | ● | ● | ● | ● | – | – | – | – |
| `SituationSheet` | ● | – | – | ● | – | ● | – | ● |
| `RevisionTrail` | ● | ● | – | ● | – | ● | ● first update | ● |
| `ForecastChart` | ● | ● | – | ● | – | ● | ● | ● |
| `DriverList` | ● | ● | – | ● | – | ● | ● | ● |
| `ChangesPanel` | ● | ● | – | ● | – | ● | ● no previous update | ● |
| `ForecastTable` | ● | ● | ● sort | ● | – | ● | ● | ● |
| `ExposureCheck` | ● | ● | ● | ● | ● no spot | ● | ● no window | ● validation |
| `ScoreCard` | ● | – | – | – | – | ● | ● too little data | ● |
| `ScoreTable` | ● | ● | – | ● | – | ● | ● mock mode | ● |
| `HorizonChart`, `HindsightChart` | ● | ● | – | ● | – | ● | ● | ● |
| `SituationTimeline` | ● | ● | ● | ● | – | ● | ● | ● |
| `SituationLog` | ● | ● | ● | ● | – | ● | ● | ● |
| `CommandMenu` | ● | ● | ● | ● | ● | – | ● | – |
| `ShortcutsDialog` | ● | – | – | ● | – | – | – | – |

Skeletons match the final height, so nothing shifts when data lands.

## 5. Assumptions and gaps

### Backend gaps

These are real API changes, not frontend mocks, because a frontend mock could not show real data in the
demo. G1, G2, G3 and G6 were approved and are built. G4 and G5 are open.

| # | Gap | Change | Priority |
|---|---|---|---|
| G1 | The API has no spot price, so there is no reference line, no spot ± 50, no spread and no spike scores | Add `spot` to forecast steps and actuals, and `spot_known_until_utc` to `Forecast`, served only from `first_usable_origin_utc`. Give mock mode invented spot published at 14:00 Helsinki. Lift the `DISPLAY_SERIES` guard. Replace the three no-spot tests with tests that prove no value appears early. Add spike scores to diagnostics. Update `schemas.py` and the API README, regenerate types, rerun the leakage check | P0 |
| G2 | Alerts exist for one hour at a time, so the timeline and log would need one request per hour | `GET /api/alerts/history?from=&to=&as_of=`, reusing `build_alerts()` | P1 |
| G3 | One request returns one forecast, so there is no forecast-vs-actual series | `GET /api/hindsight?from=&to=&lead_hours=&as_of=`, returning P10, P50, P90, actual and spot | P1 |
| G4 | Drivers carry no direction. The brief's example says "a *reduced* wind power forecast". We show "Wind power forecast", because `model.py` ranks by absolute SHAP and drops the sign | Keep the sign in a display-only column. Needs a pipeline rerun. The submission file format stays untouched | P2 |
| G5 | The conflict alert compares two outputs of one model | **Deferred by the team.** The UI shows whatever the API sends | Later |
| G6 | Situations have no recorded outcome, so "right N of M times" cannot be shown yet | Add an outcome to G2, using actuals usable at `as_of`. Each alert kind needs its own definition of "happened" | P2 |

### Assumptions

- The UI is in English, the same as the brief and the API's alert text.
- Page content shows Europe/Helsinki, while the viewing time and forecast stamp show UTC. The API always
  speaks UTC. The repeated hour on 25 Oct is labelled EEST or EET, so two rows never look identical.
- Light theme only, because `DESIGN.md` has no dark palette.
- Red-clay means up-regulation and high price, and green means down-regulation and low price. Neither is
  "good", because that depends on the position.
- "Latest" means the last forecast in the data, because this is a backtest.
- The mock has one week of forecasts, so its month view shows what exists and says so.
- The demo runs locally. Rule 6 bans hosting spot data.

### Rule 6 guardrails

- Agent screenshots and browser tests use **mock mode only**. Real-mode spot is only ever seen by a person
  in their own browser and demo video, never in chat.
- The query cache is never written to browser storage, and API payloads are never logged.
- Spot arrives only through the API, masked by viewing time. The frontend never reads a file.

### Repo constraints found

- The data hook blocks new `.json` files. `frontend/components.json` (shadcn's CLI config) needs a human to
  add it to `ALLOWED`. If not, it stays gitignored, since the build does not need it.
- The hook also blocks any path containing a folder named `data`, `results`, `work` or `submission`, so
  those folder names are avoided.
- Add to `.gitignore`: `.next/`, `next-env.d.ts`, `test-results/`, `playwright-report/`, the screenshot folder.
- New libraries must join the submission's licence list. Lightweight Charts is Apache-2.0 and needs its
  notice and a link to TradingView on the page. Both are in the Keyboard shortcuts dialog, and its chart
  logo is off.

### Stack check on this machine (7 Nov, throwaway project in this folder, now deleted)

| Checked | Result |
|---|---|
| Next 16.4.5 `build`, `start`, `dev` (Turbopack) | Work |
| Tailwind 4.3.5, `next/font` with Fraunces `opsz`, Inter, JetBrains Mono | Work |
| Lightweight Charts 5.2.1: stepped line, second pane, histogram | Render. The primitive API for the band and window shading exists |
| Playwright 1.65 with installed Edge | Works, no browser download needed |
| shadcn 4.23 with Radix | Works with `init --base radix --preset nova --no-monorepo`. Needs `next.config` and the `@/*` alias first. Its default is Base UI, so `--base radix` is required |
| Next writes its own `AGENTS.md` on `next dev` | Set `agentRules: false`, so root `AGENTS.md` stays the only rule file |
| `agent-browser` | The skill is a stub and the CLI is not installed, so screenshots use Playwright (prompt §0) |

**Biggest technical piece:** Lightweight Charts has no band series, so the P10–P90 fan and the spot ± 50
zone need a small custom primitive. Its time axis also needs Helsinki formatters.

### Worth asking Turku Energia on site

1. Do you read up-regulation as red and down-regulation as green? One token flips it.
2. Does the Exposure check match how you think about imbalance cost: volume × (imbalance price − spot)?
3. Which number do you look at first? That one leads the KPI row.

## 6. Build order and cut line

| Phase | Work |
|---|---|
| 2 Foundation | Move `frontend/` from Vite to Next, tokens and contrast script, fonts, `lib/format` with tests, primitives, `/dev/ui` |
| 3 Data | G1 (and G2, G3 if approved), regenerate types, typed client, fault wrapper, connection status, viewing time |
| 4 Screens | Shell, then Now, then Next 10 h, then Hindsight |
| 5 Verification | The prompt's §10 loop at 1280, 1440, 1920 and 768 px |

| Priority | Scope | State |
|---|---|---|
| **P0** must exist | Phase 2, G1, shell and viewing time, Now, Show what happened, Next 10 h table, Hindsight scores and Error by hours ahead, verification | Built |
| **P1** lifts Level 2 | G2 timeline and log, G3 Forecast vs actual, Revision trail, Exposure check | Built |
| **P2** only if time remains | G6 outcomes, Replay | Built |
| **P2** | G4 driver direction | Open: needs a pipeline rerun and touches `model.py`, a human decision |

## 7. Skills and agents

`skills-lock.json` lists 12 skills. `.agents/skills` and `.claude/skills` match it and are identical.

| Skill | Use | How |
|---|---|---|
| `make-interfaces-feel-better` | Every component, and a `full` review per screen in Phase 5 | Read the area file needed. The prompt wins where they differ, see ui-decisions |
| `vercel-react-best-practices` | All React code | Read only the rule files that apply, such as `bundle-dynamic-imports` and the `rerender-*` rules. TanStack Query replaces its SWR rule |
| `vercel-composition-patterns` | `ForecastChart`, panels, cards | Compound components, no boolean props, React 19 `ref` and `use()` |
| `web-design-guidelines` | Phase 5 review | Fetches its rules live, then reviews named files |
| `writing-guidelines` | UI copy and README pass | Same as above |
| `dataviz` (built in) | Every chart and KPI | Form choice, mark specs, palette validator. Already used |
| `find-skills` | Suggestions only | Nothing is installed without asking |
| `agent-browser` | Not usable yet | Needs its CLI installed. Playwright covers it |
| `vercel-react-view-transitions` | Not used | The prompt picks Motion |
| `deploy-to-vercel`, `vercel-cli-with-tokens`, `vercel-optimize` | Not used | Rule 6 bans hosting spot, and the API is local Python |
| `vercel-react-native-skills` | Not used | Web only |

**Agents.** The foundation, shell and `ForecastChart` stay in one thread, because everything depends on
them. After Now works, Next 10 h and Hindsight can go to separate worktree agents, with this plan and
`ui-decisions.md` as their handoff. Phase 5 reviews suit fresh agents, because they do not share the
builder's blind spots. Project skills load for every agent.
