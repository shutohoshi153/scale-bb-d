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
same data condition (so the false-positive rate is 5% by construction). Attribution: the cohort
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

Usage:  python run_power.py [--reps 200]
Outputs: output/power_long.csv (one row per replicate), output/power_summary.csv
"""
from __future__ import annotations
import argparse
import itertools
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=200)
    ap.add_argument("--seed", type=int, default=20260930)
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    rng = np.random.default_rng(args.seed)
    rows = []
    for gran, post, (ename, expo), design, delta in itertools.product(("5y", "1y"), POST_YEARS, EXPOSURES.items(), ("aggregate", "tracked"), DELTAS):
        n_age = 14 if gran == "5y" else 70
        for rep in range(args.reps):
            s = simulate(rng, delta, post, expo, design)
            r = design_rows(s, gran, design)
            th_c, sse_c = wls(r, "coh", n_age, s["years"])
            th_a, sse_a = wls(r, "age", n_age, s["years"])
            rows.append({"granularity": gran, "post_years": post, "exposure": ename, "design": design, "delta": delta,
                         "rep": rep, "theta_cohort": th_c, "sse_cohort": sse_c, "theta_age": th_a, "sse_age": sse_a})
        print(f"done {gran} post={post} {ename} {design} delta={delta}", flush=True)
    long = pd.DataFrame(rows)
    long.to_csv(OUT / "power_long.csv", index=False)
    summ = []
    for key, g in long.groupby(["granularity", "post_years", "exposure", "design"]):
        null = g[g.delta == 0].theta_cohort
        thr = null.quantile(0.95)
        for delta, gd in g.groupby("delta"):
            det = gd.theta_cohort > thr
            attr = gd.sse_cohort < gd.sse_age
            summ.append(dict(zip(["granularity", "post_years", "exposure", "design"], key), delta=delta,
                             power=det.mean(), attribution=(det & attr).mean(), theta_mean=gd.theta_cohort.mean(),
                             theta_sd=gd.theta_cohort.std(), threshold=thr))
    s = pd.DataFrame(summ)
    s.to_csv(OUT / "power_summary.csv", index=False)
    print(s[s.delta > 0].pivot_table(index=["design", "granularity", "exposure"], columns=["post_years", "delta"], values="power").round(2).to_string())


if __name__ == "__main__":
    main()
