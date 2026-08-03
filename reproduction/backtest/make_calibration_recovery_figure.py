"""Figure 6.3 — Calibration-recovery figure for trend-reversal diseases (liver / hypertensive).

Purpose:
    Show §6.5 ("handling diseases whose direction reverses") in a single
    figure. For liver / hypertensive, whose direction is almost always missed
    at cutoff = 2014, compare directional accuracy DA (eq. 3.11-3.12,
    sex = total) across the following 5 settings:

      (1) cutoff 2014, default        (L = +1%, P = 2035)  ... restates §6.1
      (2) cutoff 2014, recalibrated A (L = 0%,  P = 2035)  ... L swap only
      (3) cutoff 2014, recalibrated B (L = 0%,  P = 2020)  ... plus earlier convergence year
      (4) cutoff 2021, default                             ... recent reversal enters training
      (5) cutoff 2022, default                             ... same, one more year

    (2)(3) correspond to the "calibration channel" (re-setting L and P per
    disease); (4)(5) to the "data channel" (folding the recent trend into the
    training data).

Input:
    data/disease_panel_mortality.csv (falls back to the bundled prebuilt_*
    if absent).
    Note: does NOT depend on existing artifacts under output/ (DA is
    recomputed here for all settings). The default-setting values match the
    output of compute_directional_accuracy.py
    (output/directional/tables/directional_summary_total.csv).

Output:
    output/directional/tables/calibration_recovery.csv
    output/directional/figures/calibration_recovery.png
    ../../figures/fig_6_3_calibration_recovery.png (committed copy)
"""
from __future__ import annotations

import shutil

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import _paths

from experience_rate._scalebb_core.model import (  # noqa: E402
    ScaleBBConfig,
    fit_scale_bb,
    project_scale_bb,
)

SECTIONS_FIGS = _paths.HERE.parents[1] / "figures"
OUT_TABLES = _paths.OUTPUT_DIR / "directional" / "tables"
OUT_FIGS = _paths.OUTPUT_DIR / "directional" / "figures"

AGE_MIN, AGE_MAX = 20, 89
VALIDATION_END = 2024
DISEASES = ["liver", "hypertensive"]
SEX = "total"

# Common hyperparameters, identical to run_backtest.py (§3.2.3).
# L / P / cutoff are varied per setting.
COMMON_CFG = dict(
    lam_row=40.0,
    lam_col=40.0,
    diff_order=2,
    age_taper_start=90,
    age_taper_end=120,
)

# (label, cutoff, long_term_rate, convergence_year)
SETTINGS = [
    ("2014_default", 2014, 0.01, 2035),
    ("2014_L0", 2014, 0.00, 2035),
    ("2014_L0_P2020", 2014, 0.00, 2020),
    ("2021_default", 2021, 0.01, 2035),
    ("2022_default", 2022, 0.01, 2035),
]


def load_panel() -> pd.DataFrame:
    path = _paths.PANEL if _paths.PANEL.exists() else (
        _paths.DATA_DIR / "prebuilt_disease_panel_mortality.csv"
    )
    return pd.read_csv(path)


def build_matrix(panel: pd.DataFrame, disease: str, year_max: int):
    sub = panel[
        (panel["disease_id"] == disease)
        & (panel["sex"] == SEX)
        & (panel["age_low"] >= AGE_MIN)
        & (panel["age_low"] <= AGE_MAX)
        & (panel["year"] <= year_max)
    ]
    piv = sub.pivot_table(index="age_low", columns="year",
                          values="rate_per_100k", aggfunc="mean").sort_index()
    return (piv.index.to_numpy(int), piv.columns.to_numpy(int),
            piv.to_numpy(float))


def directional_accuracy(panel: pd.DataFrame, disease: str,
                         cutoff: int, L: float, P: int) -> tuple[int, float]:
    """Fit/project under the given setting and return DA (eq. 3.11-3.12).

    Definition identical to compute_directional_accuracy.py:
    changes are measured against the observed rate in the cutoff year, and
    cells with zero actual change are excluded from evaluation.
    """
    ages, years, rates = build_matrix(panel, disease, cutoff)
    cfg = ScaleBBConfig(
        last_observed_year=cutoff,
        horizon_year=VALIDATION_END,
        long_term_rate=L,
        convergence_year=P,
        **COMMON_CFG,
    )
    fit = fit_scale_bb(rates, ages=ages, years=years, config=cfg)
    fit = project_scale_bb(fit, base_year=cutoff)
    proj_years = fit.projection_years
    rate_proj = fit.rate_projected

    val_years = list(range(cutoff + 1, VALIDATION_END + 1))
    base = panel[
        (panel["disease_id"] == disease)
        & (panel["sex"] == SEX)
        & (panel["age_low"] >= AGE_MIN)
        & (panel["age_low"] <= AGE_MAX)
    ]
    act = base[base["year"].isin(val_years)].pivot_table(
        index="age_low", columns="year", values="rate_per_100k", aggfunc="mean"
    ).reindex(index=ages, columns=val_years)
    obs_cut = base[base["year"] == cutoff].set_index("age_low")[
        "rate_per_100k"].reindex(ages)

    n_eval = n_match = 0
    for j, y in enumerate(val_years):
        pj = int(np.where(proj_years == y)[0][0])
        for i in range(len(ages)):
            a_act = act.iloc[i, j]
            a_cut = obs_cut.iloc[i]
            p = rate_proj[i, pj]
            if not (pd.notna(a_act) and pd.notna(a_cut) and np.isfinite(p)):
                continue
            s_act = np.sign(a_act - a_cut)
            if s_act == 0:
                continue
            n_eval += 1
            n_match += int(s_act == np.sign(p - a_cut))
    return n_eval, round(100 * n_match / n_eval, 2)


def main():
    OUT_TABLES.mkdir(parents=True, exist_ok=True)
    OUT_FIGS.mkdir(parents=True, exist_ok=True)
    SECTIONS_FIGS.mkdir(parents=True, exist_ok=True)
    panel = load_panel()

    rows = []
    for disease in DISEASES:
        for label, cutoff, L, P in SETTINGS:
            n, da = directional_accuracy(panel, disease, cutoff, L, P)
            rows.append({"disease": disease, "setting": label, "cutoff": cutoff,
                         "long_term_rate": L, "convergence_year": P,
                         "n_cells_evaluable": n, "dir_acc_pct": da})
            print(f"{disease:14s} {label:14s} n={n:4d}  DA={da:6.2f}%")
    res = pd.DataFrame(rows)
    res.to_csv(OUT_TABLES / "calibration_recovery.csv", index=False)
    print(f"wrote {OUT_TABLES / 'calibration_recovery.csv'}")

    # ---------- Plotting ----------
    # Color = cutoff (same palette as scalebb_directional_per_cutoff.png);
    # hatch = recalibration settings at cutoff 2014 (distinguished by texture)
    styles = {
        "2014_default": dict(color="#d62728", hatch="",
                             label="cutoff 2014, default (L=+1%)"),
        "2014_L0": dict(color="#d62728", hatch="//", alpha=0.55,
                        label="cutoff 2014, recalibrated (L=0%)"),
        "2014_L0_P2020": dict(color="#d62728", hatch="xx", alpha=0.35,
                              label="cutoff 2014, recalibrated (L=0%, P=2020)"),
        "2021_default": dict(color="#ff7f0e", hatch="",
                             label="cutoff 2021, default"),
        "2022_default": dict(color="#2ca02c", hatch="",
                             label="cutoff 2022, default"),
    }
    x = np.arange(len(DISEASES))
    w = 0.16
    fig, ax = plt.subplots(figsize=(10, 5.2))
    for k, (label, *_rest) in enumerate(SETTINGS):
        st = styles[label]
        vals = [res[(res["disease"] == d) & (res["setting"] == label)]
                ["dir_acc_pct"].iloc[0] for d in DISEASES]
        bars = ax.bar(x + (k - 2) * w, vals, width=w,
                      color=st["color"], alpha=st.get("alpha", 1.0),
                      hatch=st["hatch"], edgecolor="white", linewidth=0.6,
                      label=st["label"])
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 1.2, f"{v:.1f}",
                    ha="center", va="bottom", fontsize=8)
    ax.axhline(50, color="grey", lw=0.8, ls="--", alpha=0.7,
               label="coin flip (50%)")
    ax.set_xticks(x)
    ax.set_xticklabels(DISEASES)
    ax.set_ylabel("Directional accuracy %  (higher = better)")
    ax.set_ylim(0, 100)
    ax.set_title(
        "Directional-accuracy recovery for trend-reversal diseases (sex=total)\n"
        "calibration channel (red, recalibrated L / P at cutoff 2014) vs "
        "data channel (later cutoffs)",
        fontsize=11,
    )
    ax.grid(axis="y", alpha=0.3)
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()

    out = OUT_FIGS / "calibration_recovery.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print(f"wrote {out}")

    dst = SECTIONS_FIGS / "fig_6_3_calibration_recovery.png"
    shutil.copyfile(out, dst)
    print(f"copied -> {dst.relative_to(_paths.HERE.parents[1])}")


if __name__ == "__main__":
    main()
