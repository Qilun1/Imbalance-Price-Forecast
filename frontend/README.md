# frontend

The dashboard for a production shift supervisor or an electricity trading specialist: what to check now,
what is coming in the next 10 hours, and how the forecast performed in hindsight. It is a Next.js app and
talks only to the backend API.

## Run

The dashboard needs the API running behind it. On Windows, one command from the repo root starts both and
opens the browser:

```powershell
.\start-dashboard.cmd          # real data if the pipeline has run, otherwise invented mock data
.\start-dashboard.cmd real     # the pipeline's forecasts (the submission ens_finald, its baseline and alerts)
.\start-dashboard.cmd mock     # invented mock data, needs no licensed files
```

Real data needs `static_data\static.duckdb` and `backend\infer_data\forecasts.duckdb` with the submission
loaded into it: root README, "Reproduce the submission" (step 7 loads it), plus the organiser's baseline
for both periods (`uv run python -m tools.cli baseline --period val` and `--period test`). The API opens in
its own window and, on real data, spends about 30 s after start-up building every forecast's alerts; pages
opened meanwhile wait for it. Close both windows to stop everything.

To start them by hand, use two terminals, because the API keeps its terminal busy.

```powershell
# Terminal 1, in the repo root
$env:IMBALANCE_DATA_MODE="real"     # leave this line out for mock data
.venv\Scripts\python.exe -m uvicorn backend.api.main:app --port 8000

# Terminal 2
cd frontend
npm install
npm run dev                         # http://localhost:3000, /api goes to port 8000
```

If every panel says the API is not answering, the dashboard is up but the API is not. Start the API, and
the page reconnects by itself. If the API is on another machine, set `API_ORIGIN` before starting the
dashboard.

| Command | Does |
|---|---|
| `npm run build` | Contrast check, type check and production build |
| `npm start` | Serves the production build |
| `npm run typecheck` | TypeScript only |
| `npm run lint` | ESLint |
| `npm test` | Unit tests for formatters and calculations |
| `npm run test:e2e` | Browser tests with accessibility checks. Needs the API in mock mode (`start-dashboard.cmd mock`) and the dashboard running |
| `npm run contrast` | Checks every colour pair in `src/styles/tokens.css` against WCAG AA |
| `npm run api:types` | Regenerates `src/lib/api/schema.ts` after an API change. Needs the API running |
| `node scripts/screenshots.mjs` | Every screen, width and state into `screenshots/`. Mock mode only |

Browser tests use the installed Microsoft Edge, so no browser download is needed.

## Screens

| Route | Purpose |
|---|---|
| `/` | Price history and what to check now, key figures, and the imbalance price and forecast chart with the spot price and balancing direction |
| `/next-10h` | Every quarter-hour in a table, and the Exposure check |
| `/hindsight` | Scores against the baseline and forecast vs actual, with past situations and the official scores in a side box |
| `/api-guide` | How to pull the data from the API once it runs in real mode |
| `/dev/ui` | Hidden. Every primitive in every state |

The viewing time is in the URL as `?as_of=<UTC>`, so a moment in the past can be shared as a link. The
`←` and `→` keys step one hour, `R` replays a past moment, `L` returns to the latest forecast, `1` to `4` switch
screens, and `?` lists every shortcut.

Add `?fault=slow`, `loading`, `error`, `offline` or `empty` to a URL to see a panel state. This works under
`npm run dev`, and in a build made with `NEXT_PUBLIC_API_FAULTS=on`.

## Folders

| Folder | Content |
|---|---|
| `src/app/` | Routes, root layout, fonts, global CSS |
| `src/components/ui/` | shadcn primitives, restyled to the tokens |
| `src/components/trading/` | Domain components and screens |
| `src/lib/format/` | Every number, date and time on screen |
| `src/lib/api/` | Typed client, query definitions, fault switch |
| `src/lib/realtime/` | Viewing time, replay and connection status |
| `src/lib/chart/` | Lightweight Charts views and drawing additions |
| `src/styles/tokens.css` | The only place visual values are defined |
| `scripts/` | Contrast check and screenshots |
| `tests/` | Unit tests and browser tests |

## Rules

- Visual values come from `src/styles/tokens.css`: no raw hex, pixel font sizes or one-off radii in components.
- Numbers, dates and times go through `src/lib/format`. Components never round or format.
- Action blue is `variant="primary"`, at most once per view.
- Spot prices stay out of git, logs, browser storage and hosted services (AGENTS.md rule 6). The demo runs
  locally. Automated screenshots and browser tests run on mock mode only.
- Decisions, added tokens and added libraries go in `docs/ui-decisions.md`. Component licences are in
  `docs/frontend-licences.md`.
