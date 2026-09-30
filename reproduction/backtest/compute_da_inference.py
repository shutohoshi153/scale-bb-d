"""Dependence-aware inference for directional accuracy (paper §3.3 / §6.1, added 2026-09-30; referee comment A-4).

DA as defined in (3.6) scores, for each age, one predicted sign against the
actual cumulative change from the cutoff level in every validation year.  The
cells are therefore neither independent forecasts nor independent outcomes:
cells of one age repeat the same prediction, and cells of one year share the
period shock.  This script replaces the age-block interval and the
Pesaran-Timmermann p-value with intervals that respect both dependencies:

  * two-way bootstrap: ages and validation years are resampled independently
    with replacement and the cells of the resampled age x year grid are kept
    (pigeonhole bootstrap for a two-way clustered array);
  * year-block bootstrap: validation years resampled, all ages kept.

Reported for Scale BB-D, per series (sex = total) and pooled over the six
series with a continuing decline:

  DA, the ex-post majority benchmark of the window, and two effect sizes with
  their two-way 95% intervals -- DA minus the majority benchmark (the benchmark
  is recomputed inside every resample, because it is defined on the window)
  and DA minus the DA of loglin_trend (paired on the same resampled cells).
  For the pooled rows the six series are resampled as a third cluster.

Inputs : output/directional/tables/directional_long.csv (compute_directional_accuracy.py)
Outputs: output/directional/tables/da_inference.csv
"""
from __future__ import annotations
import numpy as np
import pandas as pd

import _paths

OUT = _paths.OUTPUT_DIR / "directional" / "tables"
SIX = ["cerebrovascular", "heart_disease", "total", "cancer", "diabetes", "kidney"]
ALL = SIX + ["liver", "hypertensive"]
N_BOOT = 4000
SEED = 20260930


def grids(long_df: pd.DataFrame, disease: str, cutoff: int):
    """age x year arrays: evaluable mask, actual sign, match of Scale BB-D, match of loglin_trend."""
    d = long_df[(long_df["disease"] == disease) & (long_df["sex"] == "total") & (long_df["cutoff"] == cutoff)]
    ages = sorted(long_df["age_low"].unique())
    years = sorted(long_df.loc[long_df["cutoff"] == cutoff, "year"].unique())
    def piv(method, col):
        # every series on the same age x year grid (cells without data are not evaluable)
        return (d[d["method"] == method].pivot(index="age_low", columns="year", values=col)
                .reindex(index=ages, columns=years))
    ev = piv("scalebb", "evaluable").fillna(False).to_numpy(dtype=bool)
    sign = piv("scalebb", "actual_sign").to_numpy(dtype=float)
    m_sb = piv("scalebb", "match").fillna(False).to_numpy(dtype=bool)
    m_ll = piv("loglin_trend", "match").fillna(False).to_numpy(dtype=bool)
    return ev, sign, m_sb, m_ll


def stats(ev, sign, m_sb, m_ll):
    n = ev.sum()
    if n == 0:
        return np.nan, np.nan, np.nan
    da = m_sb[ev].mean() * 100
    down = (sign[ev] < 0).mean() * 100
    maj = max(down, 100 - down)
    ll = m_ll[ev].mean() * 100
    return da, maj, ll


def pooled_stats(parts):
    """parts: list of (ev, sign, m_sb, m_ll). DA pooled over cells; majority benchmark per series, pooled by cells."""
    n = hit = hit_ll = maj_hit = 0
    for ev, sign, m_sb, m_ll in parts:
        k = int(ev.sum())
        if k == 0:
            continue
        down = int((sign[ev] < 0).sum())
        n += k; hit += int(m_sb[ev].sum()); hit_ll += int(m_ll[ev].sum()); maj_hit += max(down, k - down)
    return (hit / n * 100, maj_hit / n * 100, hit_ll / n * 100) if n else (np.nan,) * 3


BLOCK = 3


def moving_blocks(rng, n: int, block: int = BLOCK) -> np.ndarray:
    """Indices of a moving-block resample of length n (blocks of `block` consecutive positions)."""
    block = max(1, min(block, n))
    starts = rng.integers(0, n - block + 1, size=int(np.ceil(n / block)))
    return np.concatenate([np.arange(s, s + block) for s in starts])[:n]


def ci(v):
    v = np.asarray(v, dtype=float)
    return float(np.nanpercentile(v, 2.5)), float(np.nanpercentile(v, 97.5))


def main() -> None:
    long_df = pd.read_csv(OUT / "directional_long.csv")
    rng = np.random.default_rng(SEED)
    rows = []
    for cutoff in sorted(long_df["cutoff"].unique()):
        G = {dis: grids(long_df, dis, cutoff) for dis in ALL}
        n_age, n_year = G[ALL[0]][0].shape
        # the same resampled ages / years are applied to every series (common period shocks)
        ia = rng.integers(0, n_age, size=(N_BOOT, n_age))
        iy = rng.integers(0, n_year, size=(N_BOOT, n_year))
        idis = rng.integers(0, len(SIX), size=(N_BOOT, len(SIX)))
        for dis in ALL:
            ev, sign, m_sb, m_ll = G[dis]
            da, maj, ll = stats(ev, sign, m_sb, m_ll)
            two = [stats(*(a[np.ix_(ia[b], iy[b])] for a in (ev, sign, m_sb, m_ll))) for b in range(N_BOOT)]
            yr = [stats(*(a[:, iy[b]] for a in (ev, sign, m_sb, m_ll))) for b in range(N_BOOT)]
            two = np.array(two); yr = np.array(yr)
            rows.append({"cutoff": cutoff, "series": dis, "n": int(ev.sum()), "DA": da, "majority": maj, "DA_loglin": ll,
                         "DA_minus_majority": da - maj, "DA_minus_loglin": da - ll,
                         **dict(zip(["DA_lo", "DA_hi"], ci(two[:, 0]))),
                         **dict(zip(["DA_yearblock_lo", "DA_yearblock_hi"], ci(yr[:, 0]))),
                         **dict(zip(["excess_lo", "excess_hi"], ci(two[:, 0] - two[:, 1]))),
                         **dict(zip(["vs_loglin_lo", "vs_loglin_hi"], ci(two[:, 0] - two[:, 2])))})
        parts = [G[d] for d in SIX]
        da, maj, ll = pooled_stats(parts)
        boot = []
        for b in range(N_BOOT):
            sel = [SIX[k] for k in idis[b]]
            boot.append(pooled_stats([tuple(a[np.ix_(ia[b], iy[b])] for a in G[d]) for d in sel]))
        boot = np.array(boot)
        rows.append({"cutoff": cutoff, "series": "pooled_six", "n": int(sum(p[0].sum() for p in parts)), "DA": da, "majority": maj,
                     "DA_loglin": ll, "DA_minus_majority": da - maj, "DA_minus_loglin": da - ll,
                     **dict(zip(["DA_lo", "DA_hi"], ci(boot[:, 0]))),
                     "DA_yearblock_lo": np.nan, "DA_yearblock_hi": np.nan,
                     **dict(zip(["excess_lo", "excess_hi"], ci(boot[:, 0] - boot[:, 1]))),
                     **dict(zip(["vs_loglin_lo", "vs_loglin_hi"], ci(boot[:, 0] - boot[:, 2])))})
        # [ADD 2026-09-30] sensitivity (re-review A-11): the five causes without the aggregate `total`,
        # ages and years resampled as moving blocks of BLOCK adjacent groups / consecutive years, so that
        # neighbouring ages and the consecutive shock years stay together.
        five = [d for d in SIX if d != "total"]
        parts = [G[d] for d in five]
        da, maj, ll = pooled_stats(parts)
        boot = []
        for b in range(N_BOOT):
            a_idx, y_idx = moving_blocks(rng, n_age), moving_blocks(rng, n_year)
            sel = [five[k] for k in rng.integers(0, len(five), size=len(five))]
            boot.append(pooled_stats([tuple(a[np.ix_(a_idx, y_idx)] for a in G[d]) for d in sel]))
        boot = np.array(boot)
        rows.append({"cutoff": cutoff, "series": "pooled_five_causes_block", "n": int(sum(p[0].sum() for p in parts)),
                     "DA": da, "majority": maj, "DA_loglin": ll, "DA_minus_majority": da - maj, "DA_minus_loglin": da - ll,
                     **dict(zip(["DA_lo", "DA_hi"], ci(boot[:, 0]))),
                     "DA_yearblock_lo": np.nan, "DA_yearblock_hi": np.nan,
                     **dict(zip(["excess_lo", "excess_hi"], ci(boot[:, 0] - boot[:, 1]))),
                     **dict(zip(["vs_loglin_lo", "vs_loglin_hi"], ci(boot[:, 0] - boot[:, 2])))})
    out = pd.DataFrame(rows)
    out.to_csv(OUT / "da_inference.csv", index=False)
    for cutoff in sorted(out["cutoff"].unique()):
        print(f"\n## cutoff {cutoff} (sex = total): DA [%], ex-post majority benchmark, two-way bootstrap 95% intervals\n")
        print(out[out["cutoff"] == cutoff].drop(columns="cutoff").round(1).to_markdown(index=False))


if __name__ == "__main__":
    main()
