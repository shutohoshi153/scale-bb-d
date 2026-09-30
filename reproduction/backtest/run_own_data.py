"""Run the backtest of the paper on your own rate panel (added 2026-09-30).

The paper tests the framework on cause-specific mortality because open data in
Japan contain no long incidence panel by disease, age and year.  Insurers hold
such data as claims experience.  This script runs the same fit, projection,
baselines and metrics (MAPE, directional accuracy with its majority benchmark)
on any panel in the format of data/disease_panel_mortality.csv:

    disease_id, sex, year, age_low, rate_per_100k, deaths

  disease_id      any label (a disease, a benefit, a rider)
  sex             total / male / female (series that are absent are skipped)
  year            calendar year of observation (gaps are allowed)
  age_low         lower age of a 5-year age group; ages 20-89 are used
  rate_per_100k   the rate to be projected (incidence or claim rate per 100,000 exposed)
  deaths          the number of events behind the rate (optional; not used by the equal-weight fit)

Nothing leaves your machine: the script reads the CSV, writes to output/<name>/ and prints two tables.

Usage:
    python run_own_data.py --panel /path/to/panel.csv --train-cutoff 2019 --validation-end 2024 --name own_2019

Outputs (output/<name>/tables/): validation_long.csv, validation_long_baseline.csv,
    method_comparison_MAPE_wide.csv, own_data_summary.csv
"""
from __future__ import annotations
import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--panel", required=True, help="CSV with the columns listed above")
    ap.add_argument("--train-cutoff", type=int, required=True, help="last year of the training window")
    ap.add_argument("--validation-end", type=int, required=True, help="last year of the validation window")
    ap.add_argument("--name", default="own_data", help="output sub-directory under output/ (default: own_data)")
    ap.add_argument("--trend-window", type=int, default=15, help="years used by the log-linear baseline (default 15)")
    args = ap.parse_args()

    panel = Path(args.panel).expanduser().resolve()
    if not panel.exists():
        print(f"panel not found: {panel}", file=sys.stderr)
        return 2
    env = dict(os.environ, SCALEBB_PANEL=str(panel))
    common = ["--train-cutoff", str(args.train_cutoff), "--validation-end", str(args.validation_end),
              "--output-subdir", args.name]
    for cmd in ([sys.executable, "run_backtest.py", *common],
                [sys.executable, "run_baselines.py", *common, "--trend-window", str(args.trend_window)]):
        r = subprocess.run(cmd, cwd=HERE, env=env, capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout[-2000:], r.stderr[-2000:], file=sys.stderr)
            return r.returncode

    os.environ["SCALEBB_PANEL"] = str(panel)
    sys.path.insert(0, str(HERE))
    import pandas as pd
    import compute_directional_accuracy as cda

    tables = HERE / "output" / args.name / "tables"
    long_df = cda.compute_directional(args.train_cutoff, args.name)
    da = cda.summarize(long_df)
    piv = da.pivot_table(index=["disease", "sex"], columns="method", values="dir_acc_pct")
    sb = da[da["method"] == "scalebb"].set_index(["disease", "sex"])
    mape = (pd.concat([pd.read_csv(tables / "validation_long.csv").assign(method="scalebb"),
                       pd.read_csv(tables / "validation_long_baseline.csv")])
            .query("actual_rate_per_100k > 0")
            .groupby(["disease", "sex", "method"])["abs_rel_error"].mean().mul(100).unstack("method"))
    out = pd.DataFrame({
        "MAPE_scalebb": mape["scalebb"], "MAPE_naive_last": mape["naive_last"],
        "MAPE_mean_3pts": mape["mean_3pts"], "MAPE_loglin_trend": mape["loglin_trend"],
        "DA_scalebb": piv["scalebb"], "DA_loglin_trend": piv["loglin_trend"],
        "DA_majority_benchmark": sb["majority_pct"], "n_DA_cells": sb["n_cells_evaluable"],
    }).round(2)
    out.to_csv(tables / "own_data_summary.csv")
    print(f"\nTraining to {args.train_cutoff}, validation {args.train_cutoff + 1}-{args.validation_end}. MAPE [%] and directional accuracy [%]:\n")
    print(out.to_string())
    print(f"\nWritten to {tables}")
    print("Reading guide: compare DA_scalebb with DA_majority_benchmark (the ex-post share of the prevailing direction, paper §3.3),")
    print("and MAPE_scalebb with the three baselines (paper §5). A cutoff before and after any structural break is informative (§4).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
