"""Generate and collect the figures that appear in the paper.

Does two jobs:

  1. Newly generate the explanatory figures for §3 and §4:
       fig_3_1_input_panel_overview.png      input panel overview (§3.1)
       fig_3_2_smoothing_before_after.png    smoothing before/after (§3.2.1, eq. 3.1-3.2)
       fig_3_3_blend_schematic.png           improvement-rate blending example (§3.2.2, eq. 3.5)
       fig_4_1_backtest_design.png           3-cutoff design schematic (§4.2)
  2. Collect the backtest result figures referenced by §5 from output/
       (output/ is not under git control, so the figures that appear in the
        paper are committed to figures/; if an output/ figure has not been
        generated yet, warn and skip).

All outputs go to figures/ at the repository root.
Run as the final step of run_all.sh (standalone execution also works).
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

# Destination for the paper-body figures (committed to git)
SECTIONS_FIGS = _paths.HERE.parents[1] / "figures"

AGE_MIN, AGE_MAX = 20, 89

# Hyperparameters identical to run_backtest.py (§3.2.3)
SCALE_BB_CONFIG = dict(
    long_term_rate=0.01,
    convergence_year=2035,
    lam_row=40.0,
    lam_col=40.0,
    diff_order=2,
    age_taper_start=90,
    age_taper_end=120,
)


def load_panel() -> pd.DataFrame:
    # Fall back to the bundled reference panel so this also works
    # when build_panel.py has not been run
    path = _paths.PANEL if _paths.PANEL.exists() else (
        _paths.DATA_DIR / "prebuilt_disease_panel_mortality.csv"
    )
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
# Figure 3.1 — Input panel overview (§3.1)
# ---------------------------------------------------------------------------
def make_panel_overview(panel: pd.DataFrame):
    sub = panel[(panel["sex"] == "total")]
    diseases = sorted(sub["disease_id"].unique())
    select_ages = [40, 75]
    fig, axes = plt.subplots(1, len(select_ages), figsize=(11, 4.5), sharex=True)
    cmap = plt.get_cmap("tab10")
    for ax, a in zip(axes, select_ages):
        for i, d in enumerate(diseases):
            g = sub[(sub["disease_id"] == d) & (sub["age_low"] == a)].sort_values("year")
            g = g[g["rate_per_100k"] > 0]
            ax.plot(g["year"], g["rate_per_100k"], "o-", color=cmap(i % 10),
                    label=d, markersize=3, linewidth=1.2)
        ax.set_title(f"age {a}-{a+4}")
        ax.set_xlabel("year")
        ax.set_ylabel("mortality rate (per 100k, log scale)")
        ax.set_yscale("log")
        ax.grid(alpha=0.3)
    axes[-1].legend(fontsize=7, ncol=2, loc="lower left")
    fig.suptitle(
        "Input panel: cause-specific mortality rates 1950-2024 "
        "(vital statistics table 5-15, sex=total)",
        fontsize=11,
    )
    fig.tight_layout()
    out = SECTIONS_FIGS / "fig_3_1_input_panel_overview.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print(f"wrote {out.relative_to(_paths.HERE.parents[1])}")


# ---------------------------------------------------------------------------
# Figure 3.2 — Smoothing before vs after (§3.2.1, eq. 3.1-3.2)
# ---------------------------------------------------------------------------
def make_smoothing_before_after(panel: pd.DataFrame, *, disease: str = "heart_disease",
                                sex: str = "total", cutoff: int = 2022):
    sub = panel[
        (panel["disease_id"] == disease)
        & (panel["sex"] == sex)
        & (panel["age_low"] >= AGE_MIN)
        & (panel["age_low"] <= AGE_MAX)
        & (panel["year"] <= cutoff)
    ]
    piv = sub.pivot_table(index="age_low", columns="year",
                          values="rate_per_100k", aggfunc="mean").sort_index()
    ages = piv.index.to_numpy(dtype=int)
    years = piv.columns.to_numpy(dtype=int)
    cfg = ScaleBBConfig(last_observed_year=cutoff, **SCALE_BB_CONFIG)
    fit = fit_scale_bb(piv.to_numpy(dtype=float), ages=ages, years=years, config=cfg)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    cmap = plt.get_cmap("tab10")

    # Left: cross-sections along calendar year (representative ages)
    ax = axes[0]
    for k, a in enumerate([40, 60, 75]):
        i = int(np.where(ages == a)[0][0])
        ax.plot(years, fit.rate_observed[i, :], "o", color=cmap(k % 10),
                markersize=4, alpha=0.6,
                label=f"observed, age {a}-{a+4}")
        ax.plot(years, fit.rate_smoothed[i, :], "-", color=cmap(k % 10),
                label=f"smoothed, age {a}-{a+4}")
    ax.set_title("year cross-sections (selected ages)")
    ax.set_xlabel("year")
    ax.set_ylabel("mortality rate (per 100k, log scale)")
    ax.set_yscale("log")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7)

    # Right: cross-sections along age (representative calendar years)
    ax = axes[1]
    for k, y in enumerate([1970, 2000, cutoff]):
        j = int(np.where(years == y)[0][0])
        ax.plot(ages, fit.rate_observed[:, j], "o", color=cmap(k % 10),
                markersize=4, alpha=0.6, label=f"observed, {y}")
        ax.plot(ages, fit.rate_smoothed[:, j], "-", color=cmap(k % 10),
                label=f"smoothed, {y}")
    ax.set_title("age cross-sections (selected years)")
    ax.set_xlabel("age")
    ax.set_ylabel("mortality rate (per 100k, log scale)")
    ax.set_yscale("log")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7)

    fig.suptitle(
        f"Two-dimensional Whittaker-Henderson smoothing, before vs after "
        f"(eq. 3.1-3.2)\n{disease} ({sex}), observations ≤{cutoff}",
        fontsize=11,
    )
    fig.tight_layout()
    out = SECTIONS_FIGS / "fig_3_2_smoothing_before_after.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print(f"wrote {out.relative_to(_paths.HERE.parents[1])}")


# ---------------------------------------------------------------------------
# Figure 3.3 — Blending observed improvement rates into the long-term rate (§3.2.2, eq. 3.5)
# ---------------------------------------------------------------------------
def make_blend_schematic(panel: pd.DataFrame, *, disease: str = "heart_disease",
                         sex: str = "total", cutoff: int = 2022, horizon: int = 2045):
    sub = panel[
        (panel["disease_id"] == disease)
        & (panel["sex"] == sex)
        & (panel["age_low"] >= AGE_MIN)
        & (panel["age_low"] <= AGE_MAX)
        & (panel["year"] <= cutoff)
    ]
    piv = sub.pivot_table(index="age_low", columns="year",
                          values="rate_per_100k", aggfunc="mean").sort_index()
    ages = piv.index.to_numpy(dtype=int)
    years = piv.columns.to_numpy(dtype=int)
    cfg = ScaleBBConfig(last_observed_year=cutoff, horizon_year=horizon, **SCALE_BB_CONFIG)
    fit = fit_scale_bb(piv.to_numpy(dtype=float), ages=ages, years=years, config=cfg)
    fit = project_scale_bb(fit, base_year=cutoff)

    L = SCALE_BB_CONFIG["long_term_rate"]
    P = SCALE_BB_CONFIG["convergence_year"]
    proj_years = fit.projection_years
    select_ages = [40, 60, 75]
    cmap = plt.get_cmap("tab10")

    fig, ax = plt.subplots(figsize=(9, 4.5))
    for k, a in enumerate(select_ages):
        i = int(np.where(ages == a)[0][0])
        mask = proj_years >= 2000
        ax.plot(proj_years[mask], 100 * fit.improvement_final[i, mask], "-",
                color=cmap(k % 10), label=f"age {a}-{a+4}")
    ax.axhline(100 * L, color="black", linestyle="--", linewidth=0.9,
               label=f"long-term rate L = {100*L:.0f}%")
    ax.axvline(cutoff, color="grey", linestyle=":", alpha=0.8)
    ax.axvline(P, color="grey", linestyle=":", alpha=0.8)
    ax.axvspan(cutoff, P, color="grey", alpha=0.08)
    ymax = ax.get_ylim()[1]
    ax.text(cutoff, ymax, r" $y_{\rm obs}$" + f" = {cutoff}", va="top", fontsize=9)
    ax.text(P, ymax, f" P = {P}", va="top", fontsize=9)
    ax.axhline(0, color="black", linewidth=0.6)
    ax.set_xlabel("year")
    ax.set_ylabel("annual improvement rate $i^*(x, y)$  [%]")
    ax.set_title(
        f"Blending observed improvements into the long-term rate (eq. 3.5)\n"
        f"{disease} ({sex}), cutoff {cutoff}",
        fontsize=11,
    )
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    out = SECTIONS_FIGS / "fig_3_3_blend_schematic.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print(f"wrote {out.relative_to(_paths.HERE.parents[1])}")


# ---------------------------------------------------------------------------
# Figure 4.1 — Schematic of the 3-cutoff design (§4.2)
# ---------------------------------------------------------------------------
def make_backtest_design():
    cutoffs = [2014, 2021, 2022]
    T = 2024
    fig, ax = plt.subplots(figsize=(9, 3.2))
    for row, yc in enumerate(cutoffs):
        y = len(cutoffs) - 1 - row  # 2014, 2021, 2022 from top
        ax.barh(y, yc - 1950, left=1950, height=0.5,
                color="#1f77b4", alpha=0.75,
                label="train window" if row == 0 else None)
        ax.barh(y, T - yc, left=yc, height=0.5,
                color="#d62728", alpha=0.75,
                label="validation window" if row == 0 else None)
        ax.text(yc + (T - yc) / 2, y, f"{T - yc}y", ha="center", va="center",
                color="white", fontsize=8, fontweight="bold")
        ax.text(1951, y, f"train 1950-{yc}", ha="left", va="center",
                color="white", fontsize=8)
    ax.axvspan(2020, 2022, color="grey", alpha=0.25)
    ax.text(2021, len(cutoffs) - 0.35, "COVID-19\n2020-2022", ha="center",
            va="bottom", fontsize=8)
    ax.set_yticks(range(len(cutoffs)))
    ax.set_yticklabels([f"cutoff {yc}" for yc in reversed(cutoffs)])
    ax.set_xlim(1948, 2026)
    ax.set_ylim(-0.6, len(cutoffs) + 0.1)
    ax.set_xlabel("year")
    ax.set_title("Backtest design: three fixed training cutoffs around the COVID-19 break",
                 fontsize=11)
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    out = SECTIONS_FIGS / "fig_4_1_backtest_design.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print(f"wrote {out.relative_to(_paths.HERE.parents[1])}")


# ---------------------------------------------------------------------------
# For §5 — collect the backtest result figures (output/ -> figures/)
# ---------------------------------------------------------------------------
COLLECT = {
    # §5.1
    "figures/overall_mape_bias_by_year.png": "fig_5_1_overall_mape_bias_by_year.png",
    "figures/heart_disease_total_trajectory.png": "fig_5_2_heart_disease_total_trajectory.png",
    "figures/cancer_total_trajectory.png": "fig_5_3_cancer_total_trajectory.png",
    # §5.2
    "cutoff_comparison/figures/scalebb_gap_vs_best_baseline.png":
        "fig_5_4_scalebb_gap_vs_best_baseline.png",
    # §5.3
    "cutoff_comparison/figures/scalebb_cutoff_comparison.png":
        "fig_5_5_scalebb_cutoff_comparison.png",
    # §6.2 / §6.3 (Figure 6.3 is generated directly by make_calibration_recovery_figure.py)
    "directional/figures/scalebb_directional_per_cutoff.png":
        "fig_6_1_scalebb_directional_per_cutoff.png",
    "directional/figures/scalebb_vs_loglin_directional.png":
        "fig_6_2_scalebb_vs_loglin_directional.png",
}


def collect_backtest_figures():
    for src_rel, dst_name in COLLECT.items():
        src = _paths.OUTPUT_DIR / src_rel
        if not src.exists():
            print(f"WARN: {src_rel} not generated yet, skipping (run run_all.sh first)")
            continue
        dst = SECTIONS_FIGS / dst_name
        shutil.copyfile(src, dst)
        print(f"copied output/{src_rel} -> {dst.relative_to(_paths.HERE.parents[1])}")


def main():
    SECTIONS_FIGS.mkdir(parents=True, exist_ok=True)
    panel = load_panel()
    make_panel_overview(panel)
    make_smoothing_before_after(panel)
    make_blend_schematic(panel)
    make_backtest_design()
    collect_backtest_figures()


if __name__ == "__main__":
    main()
