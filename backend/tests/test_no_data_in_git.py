"""Rule 0 of AGENTS.md: nothing tracked in git may be data (except our own models)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_no_data_tracked():
    r = subprocess.run([sys.executable, str(ROOT / "tools/hooks/check_no_data.py"), "--all"], cwd=ROOT,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_checker_blocks_data():
    sys.path.insert(0, str(ROOT))
    from tools.hooks.check_no_data import problems
    assert problems("static_data/raw/starter/spot_nordpool.csv", b"x")
    assert problems("tools/starter_package/data/inputs.parquet", b"x")
    assert problems("notes/export.csv", b"a,b")
    assert problems("tools/foo.txt", b"fi_spot_price,nordpool,,2026-06-01T00:00:00Z,1.0")
    assert problems("backend/infer_data/forecasts.duckdb", b"x")
    assert not problems("backend/artifacts/lgbm_v1/q50.txt", b"tree")
    assert not problems("backend/artifacts/lgbm_v1/meta.json", b"{}")
    assert not problems("tools/starter_package/sample_submission.csv", b"x")
    assert not problems("backend/imbalance/features.py", b"fi_spot_price")
