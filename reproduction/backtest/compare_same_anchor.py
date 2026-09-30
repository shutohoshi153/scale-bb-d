"""Trend comparison at a common starting level (paper §5.3, added 2026-09-30; referee comment A-5).

In the main comparison the methods do not start from the same level: Scale BB-D
and naive_last start from the observed rate of the cutoff year, mean_3pts from
the mean of the last three observation points, and loglin_trend from the fitted
value of its own regression line (it is not re-anchored).  Because the starting
level moves MAPE by several points (§5.3), that comparison mixes level fit and
trend fit.  This script puts every method on the same starting level and leaves
only the trend different:

  anchor = observed : level-only (= naive_last) / log-linear slope / Scale BB-D i*
  anchor = mean3    : level-only (= mean_3pts)  / log-linear slope / Scale BB-D i*
  anchor = fitted   : log-linear slope from its own fitted level (= loglin_trend as in the
                      main comparison) / Scale BB-D from its own smoothed level

Inputs : data/disease_panel_mortality.csv
         output[/cutoff_<y>]/tables/validation_long.csv, validation_long_baseline.csv
         output/base_{mean_obs,smoothed}_cutoff_<y>/tables/validation_long.csv
Outputs: output/cutoff_comparison/tables/same_anchor_cells.csv   (disease x sex x cutoff x anchor x trend)
         output/cutoff_comparison/tables/same_anchor_summary.csv (sex = total)
"""
from __future__ import annotations
import numpy as np
import pandas as pd

import _paths
import run_baselines as rbl

BASE = _paths.OUTPUT_DIR
OUT = BASE / "cutoff_comparison" / "tables"
CUTOFFS = [2014, 2021, 2022]
TREND_WINDOW = 15
KEYS = ["disease", "sex", "age_low", "year"]


def main_dir(c: int):
    return BASE / "tables" if c == 2014 else BASE / f"cutoff_{c}" / "tables"


def loglin_anchored(panel: pd.DataFrame, cutoff: int) -> pd.DataFrame:
    """Log-linear slope (same 15-year window as loglin_trend) applied from the observed and mean3 levels."""
    rbl.TRAIN_CUTOFF = cutoff
    rbl.VALIDATION_YEARS = list(range(cutoff + 1, 2025))
    rbl.TREND_WINDOW_START = cutoff - TREND_WINDOW + 1
    rows = []
    for disease in sorted(panel["disease_id"].unique()):
        for sex in ["total", "male", "female"]:
            ages, years_train, rates_train, val_actual = rbl.build_panel_for(panel, disease=disease, sex=sex)
            _, b = rbl.predict_loglin(years_train, rates_train)
            step = np.array(rbl.VALIDATION_YEARS, dtype=float) - cutoff
            growth = np.exp(b[:, None] * step[None, :])
            for anchor, level in (("observed", rbl.predict_naive_last(years_train, rates_train)),
                                  ("mean3", rbl.predict_mean_3pts(years_train, rates_train))):
                for r in rbl.make_validation_rows("loglin", disease, sex, ages, val_actual, level[:, None] * growth):
                    r["anchor"] = anchor
                    rows.append(r)
    return pd.DataFrame(rows).rename(columns={"method": "trend"})


def load(path, trend: str, anchor: str, method: str | None = None) -> pd.DataFrame:
    d = pd.read_csv(path)
    if method is not None:
        d = d[d["method"] == method]
    return d[KEYS + ["actual_rate_per_100k", "predicted_rate_per_100k"]].assign(trend=trend, anchor=anchor)


def main() -> None:
    panel = pd.read_csv(_paths.PANEL)
    frames = []
    for c in CUTOFFS:
        d = main_dir(c)
        parts = [
            load(d / "validation_long.csv", "scalebb", "observed"),
            load(BASE / f"base_mean_obs_cutoff_{c}" / "tables" / "validation_long.csv", "scalebb", "mean3"),
            load(BASE / f"base_smoothed_cutoff_{c}" / "tables" / "validation_long.csv", "scalebb", "fitted"),
            load(d / "validation_long_baseline.csv", "none", "observed", "naive_last"),
            load(d / "validation_long_baseline.csv", "none", "mean3", "mean_3pts"),
            load(d / "validation_long_baseline.csv", "loglin", "fitted", "loglin_trend"),
            loglin_anchored(panel, c)[KEYS + ["actual_rate_per_100k", "predicted_rate_per_100k", "trend", "anchor"]],
        ]
        frames.append(pd.concat(parts, ignore_index=True).assign(cutoff=c))
    df = pd.concat(frames, ignore_index=True)
    df = df[np.isfinite(df["actual_rate_per_100k"]) & (df["actual_rate_per_100k"] > 0) & np.isfinite(df["predicted_rate_per_100k"])]
    df["ape"] = (df["predicted_rate_per_100k"] - df["actual_rate_per_100k"]).abs() / df["actual_rate_per_100k"] * 100
    cells = df.groupby(["cutoff", "disease", "sex", "anchor", "trend"])["ape"].mean().rename("MAPE").reset_index()
    OUT.mkdir(parents=True, exist_ok=True)
    cells.to_csv(OUT / "same_anchor_cells.csv", index=False)

    t = cells[cells["sex"] == "total"]
    wide = t.pivot_table(index=["cutoff", "disease"], columns=["anchor", "trend"], values="MAPE")
    wide.columns = [f"{a}:{tr}" for a, tr in wide.columns]
    wide.reset_index().to_csv(OUT / "same_anchor_summary.csv", index=False)
    for c in CUTOFFS:
        print(f"\n## cutoff {c} (sex = total): MAPE [%] by starting level (anchor) and trend\n")
        x = wide.loc[c]
        x.loc["mean (8 series)"] = x.mean()
        print(x.round(2).to_markdown())
    print("\n## disease x sex cells (of 24) in which Scale BB-D has the lower MAPE, same anchor\n")
    w = cells.pivot_table(index=["cutoff", "disease", "sex"], columns=["anchor", "trend"], values="MAPE")
    rows = []
    for c in CUTOFFS:
        x = w.loc[c]
        for a in ("observed", "mean3"):
            rows.append({"cutoff": c, "anchor": a,
                         "vs loglin slope": int((x[(a, "scalebb")] < x[(a, "loglin")] - 1e-9).sum()),
                         "vs level only": int((x[(a, "scalebb")] < x[(a, "none")] - 1e-9).sum()),
                         "loglin slope vs level only": int((x[(a, "loglin")] < x[(a, "none")] - 1e-9).sum())})
    print(pd.DataFrame(rows).to_markdown(index=False))


if __name__ == "__main__":
    main()
