"""Apply the cohort-effect estimator of run_power.py to the public data of the paper (paper §7).

The public panel is cause-specific mortality in 5-year age groups (Vital Statistics of Japan), the
proxy the paper uses in place of incidence. Two post-shock years (2023-2024) are observed and no
individual follow-up exists (the "5-year groups, 2 post-shock years, aggregate" design of the power
analysis; its exposure varies by cause, sex and age and is not one of the simulated levels). For each cause and sex (the 14 independent series) the script fits

    log m(x, y) = a_x + g_x * y + b_y + theta * C(x, y)

on 2010-2019 and 2023-2024 with death counts as weights, where C is the share of the age group
born 1981-2000 (aged 20-39 in 2020) in 2023-2024, and reports theta with a model-based 95% interval,
and whether the cohort regressor fits better than a regressor for attained ages 20-39.

Usage:  python apply_public_data.py
Input:  ../backtest/data/disease_panel_mortality.csv (built by ../backtest/build_panel.py)
Output: output/public_data_theta.csv
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PANEL = HERE.parent / "backtest" / "data" / "disease_panel_mortality.csv"
PREBUILT = HERE.parent / "backtest" / "data" / "prebuilt_disease_panel_mortality.csv"
OUT = HERE / "output"
CAUSES = ["heart_disease", "cancer", "cerebrovascular", "kidney", "liver", "diabetes", "hypertensive"]
AGE_GROUPS = np.arange(20, 90, 5)


def shares(age_low, year):
    ages = age_low + np.arange(5)
    birth = year - ages
    coh = np.mean((birth >= 1981) & (birth <= 2000))
    band = np.mean((ages >= 20) & (ages <= 39))
    return coh, band


def fit(sub):
    sub = sub[(sub.year <= 2019) | (sub.year >= 2023)].copy()
    sub = sub[(sub.deaths > 0) & (sub.rate_per_100k > 0)]
    post = sub.year >= 2023
    sc = np.array([shares(a, y) for a, y in zip(sub.age_low, sub.year)])
    sub["coh"] = np.where(post, sc[:, 0], 0.0)
    sub["band"] = np.where(post, sc[:, 1], 0.0)
    ai = np.searchsorted(AGE_GROUPS, sub.age_low.to_numpy())
    t = (sub.year.to_numpy() - 2010) / 10.0
    uy = np.unique(sub.year)
    A = np.eye(AGE_GROUPS.size)[ai]
    Y = (sub.year.to_numpy()[:, None] == uy[None, 1:]).astype(float)
    yv = np.log(sub.rate_per_100k.to_numpy()); w = sub.deaths.to_numpy()
    out = {}
    for key in ("coh", "band"):
        X = np.hstack([A, A * t[:, None], Y, sub[key].to_numpy()[:, None]])
        keep = np.abs(X).sum(axis=0) > 0
        X = X[:, keep]
        sw = np.sqrt(w)
        Xw, yw = X * sw[:, None], yv * sw
        beta, *_ = np.linalg.lstsq(Xw, yw, rcond=None)
        res = yw - Xw @ beta
        dof = max(len(yw) - X.shape[1], 1)
        s2 = float(res @ res) / dof
        cov = s2 * np.linalg.pinv(Xw.T @ Xw)
        out[key] = (beta[-1], float(np.sqrt(cov[-1, -1])), float(res @ res))
    return out


def main() -> None:
    df = pd.read_csv(PANEL if PANEL.exists() else PREBUILT)
    df = df[df.age_low.isin(AGE_GROUPS) & (df.year >= 2010)]
    rows = []
    for cause in CAUSES:
        for sex in ("male", "female"):
            r = fit(df[(df.disease_id == cause) & (df.sex == sex)])
            th, se, sse_c = r["coh"]
            rows.append({"cause": cause, "sex": sex, "theta": th, "lo": th - 1.96 * se, "hi": th + 1.96 * se,
                         "cohort_fits_better_than_age": sse_c < r["band"][2]})
    out = pd.DataFrame(rows)
    OUT.mkdir(exist_ok=True)
    out.to_csv(OUT / "public_data_theta.csv", index=False)
    print(out.round(3).to_string(index=False))
    print(f"\ninterval excludes 0 in {int(((out.lo > 0) | (out.hi < 0)).sum())} of {len(out)} series; "
          f"cohort regressor preferred in {int(out.cohort_fits_better_than_age.sum())}")


if __name__ == "__main__":
    main()
