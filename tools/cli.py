"""One entry point for the whole pipeline. Run from the repo root:

    uv run python -m tools.cli <command> [options]

Commands
  ingest starter --src PATH     copy starter data into static_data and load the store
  ingest windsites              OpenStreetMap wind turbines -> static_data/raw/windsites/wind_sites_osm.csv
  ingest locations              register the (coarsened) wind sites used as NWP capacity weights
  ingest openmeteo --start D --end D [--models ecmwf_ifs,metno_nordic]   NWP single runs -> forecast_runs
  ingest fingrid --datasets 75,188 --start D --end D    Fingrid API (needs FINGRID_API_KEY)
  status                        what is in the store and in infer_data
  drop-runs --source open-meteo delete our stored NWP runs of a source (e.g. before a re-pull)
  nwp-delay [--model ecmwf_ifs] measured Open-Meteo publication delay vs the delay we assume
  features [--set v1]           (re)build the cached feature table
  train --config FILE --mode val|final
  infer --model NAME --period val|test|all
  baseline --period val|test    organiser's baseline as model "baseline-<period>"
  score --model NAME            validation score with the organiser's score.py (vs baseline)
  export --model NAME --period test|val [--out FILE]   submission CSV + organiser's validator
  compare --models A B ...       side-by-side validation scores (overall and by lead hour) from score.py output
  diagnostics [--only learning,datasize,shap,calibration]   figures -> static_data/work/diagnostics/
  leakage [--n 60]              independent availability-rule check
  single-run --model NAME --origin TS   print one 10 h forecast
  alerts build|evaluate|train|infer|leakage   event classifiers behind /api/notes
                                (docs/plans/event_notes.md); "all" runs build -> train -> infer -> leakage
  pipeline --config FILE        features -> train val -> infer val -> score -> train final
                                -> infer test -> export -> validate -> leakage
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from imbalance import forecasts, store
from imbalance.contract import TEST_FIRST_ORIGIN, VALIDATION_FIRST_ORIGIN, read_origins
from imbalance.paths import WORK_DIR, ensure_dirs


def origins_for(period: str) -> pd.DatetimeIndex:
    from tools.eval.organiser import templates
    if period == "all":
        return origins_for("val").union(origins_for("test"))
    return read_origins(templates(period)[1])


def cmd_ingest(a):
    if a.source == "starter":
        from tools.ingest.starter import run
        run(Path(a.src) if a.src else None)
    elif a.source == "windsites":
        from tools.ingest.windsites import run
        run()
    elif a.source == "locations":
        from tools.ingest.windsites import load_sites
        sites = load_sites()
        store.set_locations(sites, group="wind")
        from tools.ingest.popsites import load_pop_sites
        store.set_locations(load_pop_sites(), group="pop")
        print(f"registered {len(sites)} wind and {len(load_pop_sites())} population NWP locations, {sites['capacity_mw'].sum():.0f} MW")
    elif a.source == "openmeteo":
        from tools.ingest.openmeteo import run
        run(a.start, a.end, a.models.split(",") if a.models else None, keep_cache=not a.no_cache, group=a.group)
    elif a.source == "fingrid":
        from tools.ingest.fingrid import run
        run([int(x) for x in a.datasets.split(",")], a.start, a.end)


def cmd_status(a):
    with pd.option_context("display.width", 200, "display.max_rows", 200):
        print(store.summary())
        try:
            print(forecasts.models())
        except Exception as e:  # infer db may not exist yet
            print(f"infer_data: {e}")


def cmd_drop_runs(a):
    n = store.drop_forecast_runs(a.source)
    print(f"deleted {n} forecast_runs rows of source {a.source!r}")


def cmd_nwp_delay(a):
    from tools.ingest.openmeteo import MODELS, measure_delay
    measured = measure_delay(a.model)
    assumed = MODELS[a.model][0]
    if assumed is None:
        print(f"{a.model}: measured {measured}; no delay set yet. "
              f"Suggested: measured + 10 min, rounded up to the next full hour, + 1 h margin")
        return
    margin = assumed - measured - pd.Timedelta(minutes=10)
    print(f"{a.model}: measured {measured}, + 10 min Open-Meteo advice, assumed {assumed}, margin {margin}")
    if margin < pd.Timedelta(minutes=30):
        sys.exit("margin below 30 min: raise the delay in tools/ingest/openmeteo.py MODELS (AGENTS.md rule 4)")


def cmd_features(a):
    from tools.training.feature_table import build_feature_table
    build_feature_table(a.set)


def cmd_train(a):
    from tools.training.train import train
    train(Path(a.config), a.mode)


def cmd_infer(a):
    from imbalance.inference import infer
    from tools.training.feature_table import load_feature_table
    origins = origins_for(a.period)
    table = load_feature_table(a.set)
    out = infer(a.model, origins, features=table.drop(columns=[c for c in table if c.startswith("y_")]))
    print(f"{a.model}: {out['forecast_origin_utc'].nunique()} origins, {len(out)} rows -> infer_data")


def cmd_baseline(a):
    from tools.eval.baseline import baseline_forecast
    first = VALIDATION_FIRST_ORIGIN if a.period == "val" else TEST_FIRST_ORIGIN
    df = baseline_forecast(first, origins_for(a.period))
    forecasts.write(f"baseline-{a.period}", df)
    print(f"baseline-{a.period}: {len(df)} rows -> infer_data")


def _export(model: str, period: str, out: Path | None) -> Path:
    from tools.eval.organiser import templates, validate
    tpl, ori = templates(period)
    out = out or WORK_DIR / "submissions" / f"{model}_{period}.csv"
    forecasts.export_submission(model, tpl, out)
    ok, report = validate(out, ori)
    print(report.strip().splitlines()[0], "->", out)
    if not ok:
        print(report)
        sys.exit(1)
    return out


def cmd_export(a):
    _export(a.model, a.period, Path(a.out) if a.out else None)


def cmd_score(a):
    from tools.eval.organiser import score
    base_dir = WORK_DIR / "scores" / "baseline-val"
    if not (base_dir / "score_summary.csv").exists():
        if "baseline-val" not in set(forecasts.models()["model"]):
            cmd_baseline(argparse.Namespace(period="val"))
        ok, rep = score(_export("baseline-val", "val", None), base_dir)
        if not ok:
            sys.exit(rep)
    sub = _export(a.model, "val", None)
    ok, rep = score(sub, WORK_DIR / "scores" / a.model, base_dir / "score_summary.csv")
    lines = rep.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith("## Overall")), 0)
    print("\n".join(lines[start:start + 20]))
    if not ok:
        sys.exit(1)


def cmd_compare(a):
    """Diagnostic view of the organiser's score.py outputs (no metrics of our own)."""
    metrics = ["mae_p50", "calibration_pinball_mean", "coverage_p10_p90", "brier_spike_mean", "brier_direction"]
    rows, hz = [], []
    for m in a.models:
        d = WORK_DIR / "scores" / m
        if not (d / "score_summary.csv").exists():
            sys.exit(f"no scores for {m}: run `score --model {m}` first")
        rows.append(pd.read_csv(d / "score_summary.csv")[metrics].assign(model=m))
        hz.append(pd.read_csv(d / "score_by_horizon.csv").set_index("horizon_hour")[a.metric].rename(m))
    with pd.option_context("display.width", 200, "display.float_format", "{:.4f}".format):
        print("Overall (organiser score.py, validation period)")
        print(pd.concat(rows).set_index("model").to_string())
        print(f"\nBy lead hour: {a.metric}")
        print(pd.concat(hz, axis=1).to_string())


def cmd_diagnostics(a):
    from tools.eval.diagnostics import run
    run(tuple(a.only.split(",")) if a.only else ("learning", "datasize", "shap", "calibration"))


def cmd_leakage(a):
    from tools.eval.leakage import check
    if not check(a.set, a.n):
        sys.exit(1)


def cmd_single_run(a):
    o = pd.Timestamp(a.origin)
    o = o.tz_localize("UTC") if o.tzinfo is None else o.tz_convert("UTC")
    df = forecasts.read(a.model, pd.DatetimeIndex([o]))
    if df.empty:
        from imbalance.inference import infer
        df = infer(a.model, pd.DatetimeIndex([o]))
    cols = ["delivery_start_utc", "step", "p10", "p50", "p90", "p_up", "p_down", "p_spike_high", "p_spike_low", "top_drivers"]
    with pd.option_context("display.width", 200, "display.max_rows", 50, "display.float_format", "{:.2f}".format):
        print(df[cols].to_string(index=False))


def cmd_pipeline(a):
    import yaml
    name = yaml.safe_load(Path(a.config).read_text())["name"]
    cmd_features(argparse.Namespace(set=a.set))
    cmd_train(argparse.Namespace(config=a.config, mode="val"))
    cmd_infer(argparse.Namespace(model=f"{name}-val", period="val", set=a.set))
    cmd_score(argparse.Namespace(model=f"{name}-val"))
    cmd_train(argparse.Namespace(config=a.config, mode="final"))
    cmd_infer(argparse.Namespace(model=name, period="all", set=a.set))
    cmd_export(argparse.Namespace(model=name, period="test", out=a.out))
    cmd_leakage(argparse.Namespace(set=a.set, n=a.n))


def cmd_alerts(a):
    from tools.eval import alert_leakage
    from tools.training import alert_train
    steps = ["build", "train", "infer", "leakage"] if a.step == "all" else [a.step]
    for step in steps:
        if step == "build":
            alert_train.training_table(rebuild=True)
        elif step == "evaluate":
            alert_train.evaluate()
        elif step == "train":
            for variant in ("val", "final"):
                alert_train.train(variant)
        elif step == "infer":
            alert_train.infer_periods()
        elif step == "leakage" and not alert_leakage.check(a.n):
            sys.exit("alert leakage check failed")


def main(argv=None):
    ensure_dirs()
    p = argparse.ArgumentParser(prog="tools.cli", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("ingest"); s.add_argument("source", choices=["starter", "windsites", "locations", "openmeteo", "fingrid"])
    s.add_argument("--src"); s.add_argument("--start", default="2026-05-30"); s.add_argument("--end", default="2026-11-02T06:00")
    s.add_argument("--models"); s.add_argument("--datasets", default="75")
    s.add_argument("--no-cache", action="store_true", help="openmeteo: do not keep raw JSON")
    s.add_argument("--group", default="wind", choices=["wind", "pop"], help="openmeteo: wind sites or population centres")
    s.set_defaults(f=cmd_ingest)
    sub.add_parser("status").set_defaults(f=cmd_status)
    s = sub.add_parser("nwp-delay"); s.add_argument("--model", default="ecmwf_ifs"); s.set_defaults(f=cmd_nwp_delay)
    s = sub.add_parser("drop-runs"); s.add_argument("--source", required=True, choices=["open-meteo"])
    s.set_defaults(f=cmd_drop_runs)
    s = sub.add_parser("features"); s.add_argument("--set", default="v1"); s.set_defaults(f=cmd_features)
    s = sub.add_parser("train"); s.add_argument("--config", required=True)
    s.add_argument("--mode", choices=["val", "final"], required=True); s.set_defaults(f=cmd_train)
    s = sub.add_parser("infer"); s.add_argument("--model", required=True)
    s.add_argument("--period", choices=["val", "test", "all"], default="all"); s.add_argument("--set", default="v1")
    s.set_defaults(f=cmd_infer)
    s = sub.add_parser("baseline"); s.add_argument("--period", choices=["val", "test"], default="val")
    s.set_defaults(f=cmd_baseline)
    s = sub.add_parser("score"); s.add_argument("--model", required=True); s.set_defaults(f=cmd_score)
    s = sub.add_parser("export"); s.add_argument("--model", required=True)
    s.add_argument("--period", choices=["val", "test"], default="test"); s.add_argument("--out")
    s.set_defaults(f=cmd_export)
    s = sub.add_parser("compare"); s.add_argument("--models", nargs="+", required=True)
    s.add_argument("--metric", default="mae_p50"); s.set_defaults(f=cmd_compare)
    s = sub.add_parser("diagnostics"); s.add_argument("--only"); s.set_defaults(f=cmd_diagnostics)
    s = sub.add_parser("leakage"); s.add_argument("--set", default="v1"); s.add_argument("--n", type=int, default=60)
    s.set_defaults(f=cmd_leakage)
    s = sub.add_parser("single-run"); s.add_argument("--model", required=True); s.add_argument("--origin", required=True)
    s.set_defaults(f=cmd_single_run)
    s = sub.add_parser("pipeline"); s.add_argument("--config", required=True); s.add_argument("--set", default="v1")
    s.add_argument("--out"); s.add_argument("--n", type=int, default=60); s.set_defaults(f=cmd_pipeline)

    s = sub.add_parser("alerts")
    s.add_argument("step", choices=["build", "evaluate", "train", "infer", "leakage", "all"])
    s.add_argument("--n", type=int, default=20); s.set_defaults(f=cmd_alerts)

    a = p.parse_args(argv)
    a.f(a)


if __name__ == "__main__":
    main()
