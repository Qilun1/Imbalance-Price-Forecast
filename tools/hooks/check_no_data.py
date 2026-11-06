"""Hard rule: no data in git, except our own trained models.

Checks the files staged for commit (default) or every tracked file (--all) and exits 1 if any looks
like data. Used by .githooks/pre-commit and by backend/tests/test_no_data_in_git.py.

Allowed non-code files are listed explicitly below. Everything else with a data extension, under a
data folder, or containing spot-price rows is blocked.
"""
from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from pathlib import Path

DATA_EXTENSIONS = {
    ".csv", ".tsv", ".parquet", ".feather", ".arrow", ".duckdb", ".db", ".sqlite", ".sqlite3", ".wal",
    ".json", ".jsonl", ".ndjson", ".xlsx", ".xls", ".ods", ".nc", ".grib", ".grib2", ".grb", ".h5",
    ".hdf5", ".pkl", ".pickle", ".npy", ".npz", ".joblib", ".zip", ".gz", ".tgz", ".tar", ".7z", ".bz2",
    ".xz", ".bin", ".dat", ".pdf",
}
BLOCKED_DIRS = ("static_data/", "backend/infer_data/", "data/", "/data/", "work/", "submission/", "results/",
                "baseline_output/", "starter_package_v1/", "TurkuEnergia_SinceAI2026/")
ALLOWED = [
    # organiser's templates (no licensed data; needed by the organiser's validator and scorer)
    "tools/starter_package/sample_submission.csv",
    "tools/starter_package/forecast_origins.csv",
    "tools/starter_package/availability.csv",
    # our own trained models
    "backend/artifacts/*/*.txt",
    "backend/artifacts/*/meta.json",
    # placeholders and docs inside otherwise blocked folders
    "static_data/README.md", "static_data/**/.gitkeep", "backend/infer_data/README.md",
    # frontend tooling config (not data)
    "frontend/package.json", "frontend/package-lock.json", "frontend/tsconfig*.json",
    "frontend/*.config.json", "frontend/public/manifest.json",
]
SPOT_MARKERS = (b"fi_spot_price,nordpool", b"spot_nordpool")


def allowed(path: str) -> bool:
    return any(fnmatch.fnmatch(path, pat) for pat in ALLOWED)


def problems(path: str, content: bytes | None) -> list[str]:
    if allowed(path):
        return []
    out = []
    p = "/" + path
    if any(d in p if d.startswith("/") else path.startswith(d) or ("/" + d) in p for d in BLOCKED_DIRS):
        out.append("inside a data folder")
    if Path(path).suffix.lower() in DATA_EXTENSIONS:
        out.append(f"data file type {Path(path).suffix}")
    if content is not None and not path.endswith(("check_no_data.py", "AGENTS.md")):
        if any(m in content for m in SPOT_MARKERS) and Path(path).suffix.lower() not in {".py", ".md", ".ipynb"}:
            out.append("contains spot price rows")
        if path.endswith(".ipynb") and b"fi_spot_price,nordpool" in content:
            out.append("notebook output contains spot price rows")
    return out


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], capture_output=True, check=True).stdout


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="check every tracked file, not just staged ones")
    a = ap.parse_args(argv)
    if a.all:
        files = git("ls-files", "-z").decode().split("\0")
        read = lambda f: Path(f).read_bytes() if Path(f).is_file() else None  # noqa: E731
    else:
        files = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").decode().split("\0")
        read = lambda f: git("show", f":{f}")  # noqa: E731
    bad = []
    for f in filter(None, files):
        issues = problems(f, read(f))
        if issues:
            bad.append(f"  {f}: {', '.join(issues)}")
    if bad:
        print("BLOCKED: data must never be committed (AGENTS.md rule 0). Only code, configs, docs and our own "
              "trained models are allowed.\n" + "\n".join(bad) +
              "\nUnstage with: git restore --staged <file>", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
