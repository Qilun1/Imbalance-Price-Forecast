# Imbalance Watch (mockup)

A plain HTML/CSS/JS mockup of a notification chat on top of the event classifiers. It is kept fully
separate from the React app in `frontend/`: no build step, no dependencies, and nothing shared.

- **Plots:** the realised imbalance price (last 12 h), the P50 forecast with its P10–P90 band (next
  10 h), and the spike-high, spike-low and up-regulation probabilities per quarter-hour.
- **Chat:** posts a message when an event becomes likely (`/api/notes`), rises by 10 points or eases.
  Each message shows the probability, its calibration range, how much likelier than usual it is, a
  confidence badge, the main drivers and what is worth checking. **Show on chart** highlights the
  window on both plots, and **Why?** explains the number.
- **When it speaks:** above max(2× the usual rate, 30 %), stricter than the API's default note
  threshold, so it stays quiet in about a third of hours (measured on validation only).
- **Ask box:** a tiny local responder, not a language model: "what's going on?", "why spike high?",
  "next hour", "clear highlight".
- **Time:** ◀ ▶ step an hour, **Replay** steps forward hour by hour, and the date field jumps.
  Everything shown uses only data usable at the viewing time, because the API enforces it.

Run the API from the repo root, then open <http://127.0.0.1:8000/mockup/>:

```powershell
uv run uvicorn backend.api.main:app --port 8000                       # mock data
$env:IMBALANCE_DATA_MODE = "real"; uv run uvicorn backend.api.main:app --port 8000   # backtest
```

Real mode needs the pipeline outputs and the event classifiers (`uv run python -m tools.cli alerts all`).
