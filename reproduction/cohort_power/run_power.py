"""Power analysis: what data are needed to detect a pandemic cohort effect in incidence rates (paper §7).

Hypothesis of interest. People infected during the pandemic (2020-2022) at ages 20-39 carry a
persistent change of their later incidence rate, exp(delta), a generation-specific (cohort) effect.

Estimator (the "dedicated estimator" of the paper). Age effects, age-specific trends and a common
effect for every calendar year are held at what the data show, and the cohort deviation is read from
the post-shock years:

    log m(x, y) = a_x + g_x * y + b_y + theta * C(x, y) + e(x, y)

fitted by weighted least squares (weights = event counts) on 2010-2019 and 2023 onwards. The shock
years 2020-2022 are left out. C(x, y) is the share of the cell that belongs to the exposed cohorts
(born 1981-2000) in the post-shock years, and 0 before; with 5-year age groups the share dilutes the
signal. Detection: theta_hat above the 95th percentile of its distribution under delta = 0 for the
same data condition, estimated on a separate null set (the false-positive rate is checked on another). Attribution: the cohort
regressor fits better (lower weighted SSE) than an age regressor A(x, y) = share of the cell aged
20-39 in the post-shock years, which describes a post-shock change fixed to attained age rather than
to birth year; only a cohort can be told from that alternative, and only once the exposed band has
moved across the age groups.

Data conditions varied
  granularity   5-year age groups (as published) or single ages
  post_years    2, 5 or 10 observed years after the shock (2023-2024, -2027, -2032)
  exposure      person-years per single age and year, three illustrative levels: national (1.5 million),
                intermediate (a hypothetical value chosen between the other two; not the size of any
                insurer) and small (10,000)
  design        "aggregate": only the rate of each age x year cell is known; half of each cohort
                was infected, so the cohort effect is diluted to log(0.5 + 0.5 exp(delta)).
                "tracked": infection status is known for each person (individual follow-up), so
                each post-shock cell splits into infected and uninfected, the effect applies to the
                infected of the exposed cohorts, and the regressor is C x infected with a separate
                main effect of infection.
  delta         0 (null), 0.05, 0.10, 0.20 on the log scale

Data-generating process: log m(x, y) = log(10e-5) + (x - 20) / 69 * log(150) (10 to 1,500 per
100,000 between ages 20 and 89) + an age-specific trend of -2% to -1% a year + a period shock common
to all ages in 2020-2022 (-8%, -5%, +3%) + a common year effect N(0, 0.01). Events are over-dispersed
Poisson with variance PHI x mean (PHI = 2.5, the order of the dispersion of the public mortality panel
under the same model, see apply_public_data.py).

Replicates (third review, A-15): for every data condition, 2,000 null replicates set the detection
threshold, an independent set of 2,000 null replicates measures the false-positive rate, and 2,000
replicates per effect size measure power; power and attribution carry a 95% Wilson interval for the
Monte Carlo error. Conditions run in parallel, each on its own random stream (SeedSequence.spawn).

Usage:  python run_power.py [--reps 2000] [--null-reps 2000] [--workers N] [--long]
Outputs: output/power_summary.csv (one row per condition x effect size, with Monte Carlo intervals);
         output/power_long.csv.gz with --long (one row per replicate)
"""
from __future__ import annotations
import argparse
import itertools
import multiprocessing
import os
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
AGES = np.arange(20, 90)
PRE = np.arange(2010, 2020)
SHOCK = {2020: -0.08, 2021: -0.05, 2022: 0.03}
EXPOSED_BIRTH = (1981, 2000)          # aged 20-39 in 2020
INFECTED_SHARE = 0.5
EXPOSURES = {"national": 1.5e6, "intermediate": 1e5, "small": 1e4}   # "intermediate" is a placeholder value
POST_YEARS = (2, 5, 10)
DELTAS = (0.0, 0.05, 0.10, 0.20)
PHI = 2.5


def counts(rng, mu):
    """Over-dispersed Poisson: PHI x Poisson(mu / PHI), mean mu and variance PHI x mu."""
    return PHI * rng.poisson(mu / PHI)


def log_rate(rng):
    years = np.arange(2010, 2033)
    alpha = np.log(10e-5) + (AGES - 20) / 69 * np.log(150)
    slope = -0.02 + 0.01 * (AGES - 20) / 69
    yr = rng.normal(0, 0.01, years.size) + np.array([SHOCK.get(int(y), 0.0) for y in years])
    return years, alpha[:, None] + slope[:, None] * (years - 2010)[None, :] + yr[None, :]


def exposed(ages, years):
    birth = years[None, :] - ages[:, None]
    return ((birth >= EXPOSED_BIRTH[0]) & (birth <= EXPOSED_BIRTH[1])).astype(float)


def simulate(rng, delta, post, expo, design):
    years, lm = log_rate(rng)
    keep = np.isin(years, np.concatenate([PRE, np.arange(2023, 2023 + post)]))
    years, lm = years[keep], lm[:, keep]
    post_mask = (years >= 2023)[None, :]
    coh = exposed(AGES, years) * post_mask
    age_band = ((AGES >= 20) & (AGES <= 39))[:, None] * post_mask * 1.0
    E = np.full(lm.shape, expo)
    if design == "aggregate":
        mult = np.where(coh > 0, np.log(1 - INFECTED_SHARE + INFECTED_SHARE * np.exp(delta)), 0.0)
        d = counts(rng, np.exp(lm + mult) * E)
        return dict(years=years, d=d, E=E, coh=coh, age=age_band)
    # tracked: split post-shock cells into infected / uninfected
    d_inf = counts(rng, np.exp(lm + delta * coh) * E * INFECTED_SHARE)
    d_un = counts(rng, np.exp(lm) * E * (1 - INFECTED_SHARE))
    d_all = counts(rng, np.exp(lm) * E)
    return dict(years=years, d=d_all, E=E, coh=coh, age=age_band, d_inf=d_inf, d_un=d_un,
                E_inf=E * INFECTED_SHARE, E_un=E * (1 - INFECTED_SHARE))


def group5(a):
    """Sum a (70 x T) array over 5-year age groups -> (14 x T)."""
    return a.reshape(14, 5, -1).sum(axis=1)


def design_rows(s, granularity, design):
    """Stack cells into (y, w, X-columns) for WLS. Returns log-rate, weight, dict of regressors, ages, years."""
    years = s["years"]; post = years >= 2023
    if granularity == "5y":
        agg = lambda k: group5(s[k])
        share = lambda k: group5(s[k]) / 5.0
        ages = np.arange(14)
    else:
        agg = lambda k: s[k]
        share = lambda k: s[k]
        ages = np.arange(70)
    rows = []
    if design == "aggregate" or True:
        d, E = agg("d"), agg("E")
        coh, age = share("coh"), share("age")
        for i in range(ages.size):
            for j, y in enumerate(years):
                if design == "tracked" and post[j]:
                    continue
                rows.append((i, y, d[i, j], E[i, j], coh[i, j], age[i, j], 0.0))
    if design == "tracked":
        di, dn, Ei, En = agg("d_inf"), agg("d_un"), agg("E_inf"), agg("E_un")
        coh, age = share("coh"), share("age")
        for i in range(ages.size):
            for j, y in enumerate(years):
                if not post[j]:
                    continue
                rows.append((i, y, di[i, j], Ei[i, j], coh[i, j], age[i, j], 1.0))
                rows.append((i, y, dn[i, j], En[i, j], 0.0, 0.0, 0.0))
    r = np.array(rows, dtype=float)
    return r


def wls(r, key, n_age, years):
    """Fit a_x + g_x * t + b_y (+ infected main effect) + theta * regressor; return theta, weighted SSE."""
    i = r[:, 0].astype(int); y = r[:, 1]; d = r[:, 2]; E = r[:, 3]; inf = r[:, 6]
    reg = r[:, 4] if key == "coh" else r[:, 5]
    if (inf.sum() > 0):
        reg = reg * inf if key == "coh" else r[:, 5] * inf
    yy = np.log((d + 0.5) / E); w = d + 0.5
    uy = np.unique(y); t = (y - 2010) / 10.0
    cols = [np.eye(n_age)[i], np.eye(n_age)[i] * t[:, None]]
    Y = (y[:, None] == uy[None, 1:]).astype(float)       # year effects (first year as reference)
    cols.append(Y)
    if inf.sum() > 0:
        cols.append(inf[:, None])
    cols.append(reg[:, None])
    X = np.hstack(cols)
    sw = np.sqrt(w)
    beta, *_ = np.linalg.lstsq(X * sw[:, None], yy * sw, rcond=None)
    res = (yy - X @ beta) * sw
    return beta[-1], float(res @ res)


def wilson(k, n, z=1.96):
    """Wilson score interval for a binomial proportion k / n (Monte Carlo error of a simulated rate)."""
    if n == 0:
        return np.nan, np.nan
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return c - h, c + h


def run_condition(task):
    """All replicates of one data condition. Returns one row per replicate (theta and SSE of both regressors)."""
    (gran, post, ename, expo, design), seed, reps, null_reps = task
    rng = np.random.default_rng(seed)
    n_age = 14 if gran == "5y" else 70
    out = []
    # "null_threshold" sets the detection threshold; "null_check" is an independent null set on which the
    # false-positive rate is measured; each delta > 0 is simulated separately.
    plan = [("null_threshold", 0.0, null_reps), ("null_check", 0.0, reps)] + [("power", d, reps) for d in DELTAS if d > 0]
    for role, delta, n in plan:
        for rep in range(n):
            s = simulate(rng, delta, post, expo, design)
            r = design_rows(s, gran, design)
            th_c, sse_c = wls(r, "coh", n_age, s["years"])
            th_a, sse_a = wls(r, "age", n_age, s["years"])
            out.append((gran, post, ename, design, role, delta, rep, th_c, sse_c, th_a, sse_a))
    return out


def summarise(long):
    summ = []
    for key, g in long.groupby(["granularity", "post_years", "exposure", "design"]):
        thr = g[g.role == "null_threshold"].theta_cohort.quantile(0.95)
        for (role, delta), gd in g[g.role != "null_threshold"].groupby(["role", "delta"]):
            det = gd.theta_cohort > thr
            attr = det & (gd.sse_cohort < gd.sse_age)
            n = len(gd)
            plo, phi = wilson(int(det.sum()), n)
            alo, ahi = wilson(int(attr.sum()), n)
            summ.append(dict(zip(["granularity", "post_years", "exposure", "design"], key), delta=delta, n_reps=n,
                             power=det.mean(), power_lo=plo, power_hi=phi,
                             attribution=attr.mean(), attribution_lo=alo, attribution_hi=ahi,
                             theta_mean=gd.theta_cohort.mean(), theta_sd=gd.theta_cohort.std(), threshold=thr))
    return pd.DataFrame(summ)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=2000, help="replicates per delta, and for the independent null check")
    ap.add_argument("--null-reps", type=int, default=2000, help="null replicates used only to set the detection threshold")
    ap.add_argument("--seed", type=int, default=20260930)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--long", action="store_true", help="also write one row per replicate (output/power_long.csv.gz)")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    conds = [(g, p, e, x, d) for g, p, (e, x), d in itertools.product(("5y", "1y"), POST_YEARS, EXPOSURES.items(), ("aggregate", "tracked"))]
    seeds = np.random.SeedSequence(args.seed).spawn(len(conds))
    tasks = [(c, s, args.reps, args.null_reps) for c, s in zip(conds, seeds)]
    with multiprocessing.Pool(args.workers) as pool:
        rows = [r for chunk in pool.imap(run_condition, tasks) for r in chunk]
    long = pd.DataFrame(rows, columns=["granularity", "post_years", "exposure", "design", "role", "delta", "rep",
                                       "theta_cohort", "sse_cohort", "theta_age", "sse_age"])
    if args.long:
        long.to_csv(OUT / "power_long.csv.gz", index=False)
    s = summarise(long)
    s.to_csv(OUT / "power_summary.csv", index=False)
    print(s[s.delta > 0].pivot_table(index=["design", "granularity", "exposure"], columns=["post_years", "delta"], values="power").round(2).to_string())
    print("\nfalse-positive rate on the independent null set:")
    print(s[s.delta == 0].pivot_table(index=["design", "granularity", "exposure"], columns="post_years", values="power").round(3).to_string())


if __name__ == "__main__":
    main()
