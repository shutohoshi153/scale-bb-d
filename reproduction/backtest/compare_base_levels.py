"""Sensitivity of Scale BB-D point accuracy to the projection base level (paper §5, added 2026-09-03).

Equation (3.6) starts the projection from the base-year rate m(x, y_0). Three choices of
that level are compared at the three cutoffs of §4 (run_all.sh produces the extra runs):

  observed  : the observed rate at the cutoff year (the paper's definition; main results)
  mean_obs  : the mean of the last 3 observation points (the level anchor of mean_3pts)
  smoothed  : the Phase 1 smoothed rate at the cutoff year (the implementation before 2026-09-03)

Inputs : output[/cutoff_<y>]/tables/validation_summary.csv          (observed, main run)
         output/base_<level>_cutoff_<y>/tables/validation_summary.csv (sensitivity runs)
         output[/cutoff_<y>]/tables/validation_summary_baseline.csv
Output : output/cutoff_comparison/tables/base_level_sensitivity.csv
"""
from __future__ import annotations
import pandas as pd
import _paths

BASE = _paths.OUTPUT_DIR
CUTOFFS = [2014, 2021, 2022]
LEVELS = ["observed", "mean_obs", "smoothed"]


def main_dir(c: int):
    return BASE if c == 2014 else BASE / f"cutoff_{c}"


def main() -> None:
    rows = []
    for c in CUTOFFS:
        bl = pd.read_csv(main_dir(c) / "tables" / "validation_summary_baseline.csv")
        best = bl.groupby(["disease", "sex"])["MAPE_pct"].min().rename("best_baseline")
        best_name = bl.loc[bl.groupby(["disease", "sex"])["MAPE_pct"].idxmin()].set_index(["disease", "sex"])["method"].rename("best_baseline_name")
        for lvl in LEVELS:
            d = main_dir(c) if lvl == "observed" else BASE / f"base_{lvl}_cutoff_{c}"
            f = d / "tables" / "validation_summary.csv"
            if not f.exists():
                print(f"skip {lvl} cutoff {c}: {f} not found")
                continue
            sb = pd.read_csv(f).set_index(["disease", "sex"])[["MAPE_pct", "bias_per100k"]]
            m = sb.join(best).join(best_name).reset_index()
            m["cutoff"] = c
            m["base_level"] = lvl
            m["gap_pp"] = (m["MAPE_pct"] - m["best_baseline"]).round(2)
            rows.append(m)
    out = pd.concat(rows, ignore_index=True)
    (BASE / "cutoff_comparison" / "tables").mkdir(parents=True, exist_ok=True)
    out.to_csv(BASE / "cutoff_comparison" / "tables" / "base_level_sensitivity.csv", index=False)
    print("wrote base_level_sensitivity.csv")
    t = out[out["sex"] == "total"]
    print(t.pivot_table(index=["cutoff", "disease"], columns="base_level", values="MAPE_pct").round(2).to_string())
    print("\n24-cell wins vs best baseline:")
    print(out.assign(win=out["gap_pp"] < 0).groupby(["cutoff", "base_level"])["win"].sum().unstack().to_string())
    print("\nmean gap [pp], six declining series, sex=total:")
    six = ["total", "cancer", "diabetes", "cerebrovascular", "heart_disease", "kidney"]
    print(t[t["disease"].isin(six)].groupby(["cutoff", "base_level"])["gap_pp"].mean().unstack().round(2).to_string())


if __name__ == "__main__":
    main()
