# frontend

React + Vite + TypeScript dashboard. Talks only to the backend API.

| Folder | Content |
|---|---|
| `src/api/` | Typed client for the backend |
| `src/components/` | Charts and cards: fan chart, direction strip, spike risk, alerts, time slider |
| `src/pages/` | Now, Next 10 h, Performance |
| `src/hooks/` | Data-fetching and state hooks |
| `src/styles/` | Styles |

## Run

Start the API first (see `backend/api/README.md`), then:

```powershell
npm install
npm run dev            # http://localhost:5173, /api is proxied to port 8000
npm run api:types      # regenerate src/api/schema.ts after an API change (API must be running)
npm run build          # type check and production build
```

So far only the wiring exists: the typed client in `src/api/` and a one-line connection check in
`src/App.tsx`. Pages, layout, charts and styling are still to be decided.
