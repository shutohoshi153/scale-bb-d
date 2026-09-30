"""Fixed-horizon rolling-origin evaluation (paper §5.2, added 2026-09-30; referee comment A-3).

The 3-cutoff comparison (2014 / 2021 / 2022) mixes two things: whether the
pandemic years are in the training window, and the length of the forecast
window (10 / 3 / 2 years).  This script holds the horizon fixed: for every
training cutoff 2014, 2015, ..., 2023 it takes the forecast exactly h = 1, 2, 3
years ahead (target year = cutoff + h <= 2024) and reports MAPE and the mean
relative bias per method, so that adjacent cutoffs can be compared at the same
horizon.

Inputs : output/ (cutoff 2014) and output/cutoff_<y>/ for y = 2015..2023
         (produced by run_backtest.py / run_baselines.py, see run_all.sh)
Outputs: output/cutoff_comparison/tables/fixed_horizon_cells.csv   (disease x sex x cutoff x h x method)
         output/cutoff_comparison/tables/fixed_horizon_summary.csv (sex = total, mean over the 8 series)
"""
from __future__ import annotations
import pandas as pd

import _paths

BASE = _paths.OUTPUT_DIR
OUT = BASE / "cutoff_comparison" / "tables"
CUTOFFS = list(range(2014, 2024))
HORIZONS = [1, 2, 3]
METHODS = ["scalebb", "naive_last", "mean_3pts", "loglin_trend"]


def load(cutoff: int) -> pd.DataFrame:
    d = BASE / "tables" if cutoff == 2014 else BASE / f"cutoff_{cutoff}" / "tables"
    sb = pd.read_csv(d / "validation_long.csv").assign(method="scalebb")
    bl = pd.read_csv(d / "validation_long_baseline.csv")
    df = pd.concat([sb, bl], ignore_index=True)
    df["cutoff"] = cutoff
    df["h"] = df["year"] - cutoff
    return df[df["h"].isin(HORIZONS)]


def main() -> None:
    df = pd.concat([load(c) for c in CUTOFFS], ignore_index=True)
    df = df[df["actual_rate_per_100k"] > 0]
    cells = (df.groupby(["cutoff", "h", "disease", "sex", "method"])
             .agg(MAPE=("abs_rel_error", lambda s: s.mean() * 100),
                  bias=("rel_error", lambda s: s.mean() * 100),
                  n=("abs_rel_error", "size")).reset_index())
    cells["target_year"] = cells["cutoff"] + cells["h"]
    OUT.mkdir(parents=True, exist_ok=True)
    cells.to_csv(OUT / "fixed_horizon_cells.csv", index=False)

    t = cells[cells["sex"] == "total"]
    summ = (t.groupby(["h", "cutoff", "method"])[["MAPE", "bias"]].mean().reset_index())
    wide = summ.pivot(index=["h", "cutoff"], columns="method", values="MAPE")[METHODS]
    wide["best_baseline"] = wide[METHODS[1:]].min(axis=1)
    wide["gap_pp"] = wide["scalebb"] - wide["best_baseline"]
    wide["scalebb_bias"] = summ[summ["method"] == "scalebb"].set_index(["h", "cutoff"])["bias"]
    wide = wide.reset_index()
    wide["target_year"] = wide["cutoff"] + wide["h"]
    wide.to_csv(OUT / "fixed_horizon_summary.csv", index=False)
    for h in HORIZONS:
        print(f"\n## h = {h} (sex = total, mean over the 8 series): MAPE [%], gap to the best baseline [pp], Scale BB-D bias [%]\n")
        print(wide[wide["h"] == h].drop(columns="h").round(2).to_markdown(index=False))


if __name__ == "__main__":
    main()
