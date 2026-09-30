"""Deaths-weighted and age-restricted MAPE (paper §5, added 2026-09-03; review B-10).

The plain MAPE of §3.4.2 weights every validation cell equally, so it is dominated by
the low-count young-age cells whose percentage errors are large but financially
immaterial. This script re-aggregates the same validation cells with two alternative
weightings, for Scale BB-D and the three baselines, at the three cutoffs of §4:

  * MAPE_dw  : deaths-weighted MAPE  = sum(d * |rel err|) / sum(d), d = actual deaths in the cell
  * MAPE_40  : plain MAPE restricted to ages 40-89

Inputs : output[/cutoff_<y>]/tables/validation_long.csv, validation_long_baseline.csv,
         data/disease_panel_mortality.csv (deaths column)
Output : output/cutoff_comparison/tables/weighted_mape.csv
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import _paths

BASE = _paths.OUTPUT_DIR
CUTOFFS = [(2014, None), (2021, "cutoff_2021"), (2022, "cutoff_2022")]
KEY = ["disease", "sex", "age_low", "year"]


def load(cutoff: int, sub: str | None) -> pd.DataFrame:
    d = (BASE / sub if sub else BASE) / "tables"
    sb = pd.read_csv(d / "validation_long.csv")[KEY + ["actual_rate_per_100k", "predicted_rate_per_100k"]]
    sb["method"] = "scalebb"
    bl = pd.read_csv(d / "validation_long_baseline.csv")[["method"] + KEY + ["actual_rate_per_100k", "predicted_rate_per_100k"]]
    df = pd.concat([sb, bl], ignore_index=True)
    df["cutoff"] = cutoff
    return df


def main() -> None:
    panel = pd.read_csv(_paths.PANEL).rename(columns={"disease_id": "disease"})[KEY + ["deaths"]]
    df = pd.concat([load(c, s) for c, s in CUTOFFS], ignore_index=True).merge(panel, on=KEY, how="left")
    df = df[(df["actual_rate_per_100k"] > 0) & df["predicted_rate_per_100k"].notna()].copy()
    df["are"] = (df["predicted_rate_per_100k"] - df["actual_rate_per_100k"]).abs() / df["actual_rate_per_100k"]
    rows = []
    for (c, m, dis, sex), g in df.groupby(["cutoff", "method", "disease", "sex"]):
        w = g["deaths"].fillna(0.0)
        rows.append({"cutoff": c, "method": m, "disease": dis, "sex": sex, "n_cells": len(g),
                     "MAPE_pct": round(g["are"].mean() * 100, 2),
                     "MAPE_dw_pct": round(float((g["are"] * w).sum() / w.sum() * 100), 2) if w.sum() > 0 else np.nan,
                     "MAPE_40_pct": round(g[g["age_low"] >= 40]["are"].mean() * 100, 2)})
    out = pd.DataFrame(rows)
    (BASE / "cutoff_comparison" / "tables").mkdir(parents=True, exist_ok=True)
    out.to_csv(BASE / "cutoff_comparison" / "tables" / "weighted_mape.csv", index=False)
    print("wrote weighted_mape.csv")
    t = out[out["sex"] == "total"]
    for col in ["MAPE_pct", "MAPE_dw_pct", "MAPE_40_pct"]:
        print(f"\n=== {col} (sex=total) ===")
        print(t.pivot_table(index=["cutoff", "disease"], columns="method", values=col).round(2).to_string())


if __name__ == "__main__":
    main()
