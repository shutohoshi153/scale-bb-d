"""Power of the cohort-effect estimator on the public panel itself (paper §7.3, Table 7.2 panel A).

Third review, A-14: the stylised grid of run_power.py does not place the public panel, whose exposure
and event counts vary by cause, sex and age. This script simulates each of the 14 independent
cause x sex series with its own structure and runs exactly the estimator of apply_public_data.py:

  exposure   the population of each sex x 5-year age group (20-85) and year, taken from the public panel
             as deaths / rate for all causes; years after 2024 keep the 2024 population
  base rate  a WLS fit (death-count weights) of log m = a_x + g_x * t + b_y to the series on the
             pre-shock years of the panel (2010, 2013-2019); the true log rate is a_x + g_x * t
             extrapolated, plus a common year effect drawn with the standard deviation of the fitted b_y;
             the rate is deaths / population; age groups with deaths in fewer than 5 of the 8 pre-shock
             years take their pooled rate, flat
  counts     over-dispersed Poisson with the dispersion of the same fit (Pearson statistic, at least 1)
  effect     half of each exposed cohort (born 1981-2000) is infected and its later rate is exp(delta)
             times higher, so the rate of a cell rises by the factor 1 + C x 0.5 x (exp(delta) - 1),
             with C the exposed share of the cell; no individual follow-up (aggregate design)
  years      the pre-shock years of the panel and 2, 5 or 10 post-shock years from 2023; 2020-2022
             are simulated but left out by the estimator, as in apply_public_data.py

Replicates as in run_power.py: 2,000 null replicates set the threshold (95th percentile of theta),
an independent 2,000 measure the false-positive rate, and 2,000 per effect size measure power, with
95% Wilson intervals. The same assumptions as the grid apply (the estimator's model is right, the
exposed band is fixed in advance), so the figures are upper bounds.

Usage:  python public_panel_power.py [--reps 2000] [--null-reps 2000] [--workers N]
Output: output/public_panel_power.csv, output/public_panel_structure.csv (fitted dispersion, year-effect sd,
        deaths at ages 20-44 in 2019 for each series)
"""
from __future__ import annotations
import argparse
import itertools
import multiprocessing
import os
from pathlib import Path
import numpy as np
import pandas as pd

from apply_public_data import AGE_GROUPS, CAUSES, PANEL, PREBUILT, fit, shares
from run_power import wilson

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
POST_YEARS = (2, 5, 10)
DELTAS = (0.10, 0.20)
INFECTED_SHARE = 0.5
MIN_YEARS = 5   # of the 8 pre-shock years


def load():
    df = pd.read_csv(PANEL if PANEL.exists() else PREBUILT)
    return df[df.age_low.isin(AGE_GROUPS) & (df.year >= 2010)]


def population(df, sex):
    t = df[(df.disease_id == "total") & (df.sex == sex)]
    t = t.assign(pop=t.deaths / (t.rate_per_100k / 1e5))
    return t.pivot(index="age_low", columns="year", values="pop").reindex(AGE_GROUPS)


def structure(sub, pop):
    """Fit log m = a_x + g_x t + b_y on the pre-shock years; return truth parameters and dispersion.

    The rate is deaths / population (the published rate is rounded to 0.1 per 100,000 population, which
    for small causes at young ages turns cells with deaths into zero rates)."""
    pre = sub[sub.year <= 2019].copy()
    pre["pop"] = [pop.at[x, y] for x, y in zip(pre.age_low, pre.year)]
    pre["m"] = pre.deaths / pre["pop"]
    fitd = pre[pre.deaths > 0]
    ai = np.searchsorted(AGE_GROUPS, fitd.age_low.to_numpy())
    t = (fitd.year.to_numpy() - 2010) / 10.0
    uy = np.unique(pre.year)
    A = np.eye(AGE_GROUPS.size)[ai]
    Y = (fitd.year.to_numpy()[:, None] == uy[None, 1:]).astype(float)
    X = np.hstack([A, A * t[:, None], Y])
    y = np.log(fitd.m.to_numpy()); w = fitd.deaths.to_numpy()
    sw = np.sqrt(w)
    beta, *_ = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)
    res = (y - X @ beta) * sw
    phi = max(1.0, float(res @ res) / max(len(y) - X.shape[1], 1))
    n = AGE_GROUPS.size
    a, g = beta[:n].copy(), beta[n:2 * n].copy()
    # Age groups with deaths in fewer than MIN_YEARS pre-shock years have no usable level or trend:
    # they take the pooled rate of those years, flat.
    for i, x in enumerate(AGE_GROUPS):
        cell = pre[pre.age_low == x]
        if int((cell.deaths > 0).sum()) < MIN_YEARS:
            a[i], g[i] = np.log((cell.deaths.sum() + 0.5) / cell["pop"].sum()), 0.0
    b = np.concatenate([[0.0], beta[2 * n:]])
    return dict(a=a, g=g, year_sd=float(np.std(b - b.mean(), ddof=1)), phi=phi, pre_years=uy)


def simulate_series(rng, st, pop, post, delta):
    years = np.concatenate([st["pre_years"], np.arange(2023, 2023 + post)])
    lm = st["a"][:, None] + st["g"][:, None] * ((years - 2010) / 10.0)[None, :] + rng.normal(0, st["year_sd"], years.size)[None, :]
    E = np.column_stack([pop[min(int(y), 2024)].to_numpy() for y in years])
    C = np.array([[shares(a, y)[0] if y >= 2023 else 0.0 for y in years] for a in AGE_GROUPS])
    mu = np.exp(lm) * E * (1 + C * INFECTED_SHARE * (np.exp(delta) - 1))
    d = st["phi"] * rng.poisson(mu / st["phi"])
    rate = np.where(E > 0, d / E * 1e5, 0.0)
    return pd.DataFrame({"age_low": np.repeat(AGE_GROUPS, years.size), "year": np.tile(years, AGE_GROUPS.size),
                         "deaths": d.ravel(), "rate_per_100k": rate.ravel()})


def run_series(task):
    (cause, sex, post), seed, reps, null_reps, st, pop = task
    rng = np.random.default_rng(seed)
    plan = [("null_threshold", 0.0, null_reps), ("null_check", 0.0, reps)] + [("power", d, reps) for d in DELTAS]
    out = []
    for role, delta, n in plan:
        for rep in range(n):
            r = fit(simulate_series(rng, st, pop, post, delta))
            out.append((cause, sex, post, role, delta, r["coh"][0], r["coh"][2] < r["band"][2]))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--null-reps", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20261001)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    df = load()
    pops = {s: population(df, s) for s in ("male", "female")}
    structs, rows_struct = {}, []
    for cause, sex in itertools.product(CAUSES, ("male", "female")):
        st = structure(df[(df.disease_id == cause) & (df.sex == sex)], pops[sex])
        structs[cause, sex] = st
        d19 = df[(df.disease_id == cause) & (df.sex == sex) & (df.year == 2019) & df.age_low.between(20, 40)].deaths.sum()
        rows_struct.append({"cause": cause, "sex": sex, "dispersion": st["phi"], "year_effect_sd": st["year_sd"],
                            "deaths_age20_44_2019": d19})
    pd.DataFrame(rows_struct).to_csv(OUT / "public_panel_structure.csv", index=False)
    keys = [(c, s, p) for (c, s), p in itertools.product(structs, POST_YEARS)]
    seeds = np.random.SeedSequence(args.seed).spawn(len(keys))
    tasks = [(k, sd, args.reps, args.null_reps, structs[k[0], k[1]], pops[k[1]]) for k, sd in zip(keys, seeds)]
    with multiprocessing.Pool(args.workers) as pool:
        rows = [r for chunk in pool.imap(run_series, tasks) for r in chunk]
    long = pd.DataFrame(rows, columns=["cause", "sex", "post_years", "role", "delta", "theta", "cohort_better"])
    summ = []
    for (cause, sex, post), g in long.groupby(["cause", "sex", "post_years"], sort=False):
        thr = g[g.role == "null_threshold"].theta.quantile(0.95)
        for (role, delta), gd in g[g.role != "null_threshold"].groupby(["role", "delta"]):
            det = gd.theta > thr
            attr = det & gd.cohort_better
            n = len(gd)
            plo, phi = wilson(int(det.sum()), n)
            alo, ahi = wilson(int(attr.sum()), n)
            summ.append({"cause": cause, "sex": sex, "post_years": post, "delta": delta, "n_reps": n,
                         "power": det.mean(), "power_lo": plo, "power_hi": phi,
                         "attribution": attr.mean(), "attribution_lo": alo, "attribution_hi": ahi,
                         "theta_sd": gd.theta.std(), "threshold": thr})
    s = pd.DataFrame(summ)
    s.to_csv(OUT / "public_panel_power.csv", index=False)
    print(s[s.delta > 0].pivot_table(index=["cause", "sex"], columns=["delta", "post_years"], values="power", sort=False).round(2).to_string())
    print("\nfalse-positive rate on the independent null set:")
    print(s[s.delta == 0].pivot_table(index=["cause", "sex"], columns="post_years", values="power", sort=False).round(3).to_string())


if __name__ == "__main__":
    main()
