"""Record what produced output/ (added 2026-09-30; referee comment A-0).

Writes output/MANIFEST.json with the SHA-256 of the input data and of the
algorithm core, the git commit of the code, the smoothing and projection
settings, the library versions and the time of the run, and copies the small
summary tables behind the paper's Tables 5.1-6.5 to reference_tables/ so that
they can be read without re-running the pipeline (output/ is not under version
control).  Run at the end of run_all.sh.
"""
from __future__ import annotations
import hashlib
import json
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import scipy

import _paths
import run_backtest as rb

HERE = Path(__file__).resolve().parent
REF = HERE / "reference_tables"
TABLES = [
    "tables/validation_summary.csv", "tables/validation_summary_baseline.csv",
    "cutoff_2021/tables/validation_summary.csv", "cutoff_2021/tables/validation_summary_baseline.csv",
    "cutoff_2022/tables/validation_summary.csv", "cutoff_2022/tables/validation_summary_baseline.csv",
    "cutoff_comparison/tables/base_level_sensitivity.csv", "cutoff_comparison/tables/fixed_horizon_summary.csv",
    "cutoff_comparison/tables/same_anchor_summary.csv",
    "directional/tables/directional_summary_total.csv", "directional/tables/da_inference.csv",
    "directional/tables/rolling_origin_da.csv", "directional/tables/directional_winloss.csv",
    "directional/tables/calibration_recovery.csv",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def main() -> None:
    core = _paths.VENDOR_DIR / "experience_rate" / "_scalebb_core"
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": git("rev-parse", "HEAD"),
        "git_dirty_files_in_package": [l for l in git("status", "--porcelain", "--", ".").splitlines() if l],
        "inputs": {p.relative_to(HERE).as_posix(): sha256(p)
                   for p in (_paths.RAW_VITAL_CSV, _paths.DISEASE_MAPPING, _paths.PANEL) if p.exists()},
        "algorithm_core": {p.name: sha256(p) for p in sorted(core.glob("*.py"))},
        "settings": {"scale_bb": rb.SCALE_BB_CONFIG, "base_level_main_results": "observed",
                     "age_range": [rb.AGE_MIN, rb.AGE_MAX], "cutoffs_main": [2014, 2021, 2022],
                     "cutoffs_rolling": list(range(2015, 2024)), "loglin_trend_window_years": 15},
        "versions": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
                     "scipy": scipy.__version__},
        "reference_tables": {},
    }
    REF.mkdir(exist_ok=True)
    for rel in TABLES:
        src = _paths.OUTPUT_DIR / rel
        if not src.exists():
            continue
        dst = REF / rel.replace("/tables/", "__").replace("tables/", "main__").replace("/", "__")
        shutil.copyfile(src, dst)
        manifest["reference_tables"][dst.name] = {"source": f"output/{rel}", "sha256": sha256(dst)}
    text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    (_paths.OUTPUT_DIR / "MANIFEST.json").write_text(text, encoding="utf-8")
    (REF / "MANIFEST.json").write_text(text, encoding="utf-8")
    print(f"wrote output/MANIFEST.json and {len(manifest['reference_tables'])} tables to {REF.name}/")


if __name__ == "__main__":
    main()
