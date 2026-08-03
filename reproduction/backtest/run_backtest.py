"""ScaleBB backtest: fit on data ≤ TRAIN_CUTOFF, project & validate forward.

Reads the panel produced by build_panel.py and runs the vendored Scale BB core
(KDB/src/experience_rate/_scalebb_core/model.py) per (disease, sex).

CLI args (all optional, defaults match the original 2014/2024 setup):
  --train-cutoff INT     last year used for training (default 2014)
  --validation-end INT   last year of validation window (default 2024)
  --output-subdir STR    subdir under output/ to write tables/figures into.
                         empty string writes into output/ (legacy behaviour).

Outputs (under BackTest_ScaleBB_2015_2024/output[/<subdir>]/):
  tables/fit_long.csv             tidy fit/projection result, all diseases/sexes
  tables/validation_long.csv      predicted vs actual on validation window
  tables/validation_summary.csv   per-disease/sex aggregated error metrics
  tables/validation_by_year.csv   per-disease/sex/year metrics
  figures/<disease>_<sex>_trajectory.png  observed/projected rate trajectories
  figures/overall_mape_bias_by_year.png   per-disease MAPE/bias trend
"""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# [REPRO] Paths and vendored core consolidated in the self-contained path layer
# (originally: ROOT=parents[2], with KDB/src added to sys.path)
import _paths

from experience_rate._scalebb_core.model import (  # noqa: E402
    ScaleBBConfig,
    fit_scale_bb,
    project_scale_bb,
)

PANEL = _paths.PANEL
AGE_MIN, AGE_MAX = 20, 89  # ages with non-trivial death rates and full mapping coverage

# Mutable globals — set in main() from CLI args. Defaults reproduce the original run.
TRAIN_CUTOFF: int = 2014
VALIDATION_YEARS: list[int] = list(range(2015, 2025))
OUT_TABLES: Path = _paths.OUTPUT_DIR / "tables"
OUT_FIGS: Path = _paths.OUTPUT_DIR / "figures"

# ScaleBB hyperparameters (mirrors KDB defaults in config.yaml > scalebb_presets)
SCALE_BB_CONFIG = dict(
    long_term_rate=0.01,
    convergence_year=2035,
    lam_row=40.0,
    lam_col=40.0,
    diff_order=2,
    age_taper_start=90,
    age_taper_end=120,
)


def build_matrix(df: pd.DataFrame, *, disease: str, sex: str, year_max: int):
    sub = df[
        (df["disease_id"] == disease)
        & (df["sex"] == sex)
        & (df["age_low"] >= AGE_MIN)
        & (df["age_low"] <= AGE_MAX)
        & (df["year"] <= year_max)
    ]
    piv = sub.pivot_table(
        index="age_low", columns="year", values="rate_per_100k", aggfunc="mean"
    ).sort_index()
    ages = piv.index.to_numpy(dtype=int)
    years = piv.columns.to_numpy(dtype=int)
    rates = piv.to_numpy(dtype=float)
    return ages, years, rates


def run_one(df: pd.DataFrame, *, disease: str, sex: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    ages, years_train, rates_train = build_matrix(df, disease=disease, sex=sex, year_max=TRAIN_CUTOFF)
    if rates_train.size == 0 or np.all(~np.isfinite(rates_train)):
        return pd.DataFrame(), pd.DataFrame()

    cfg = ScaleBBConfig(
        last_observed_year=TRAIN_CUTOFF,
        horizon_year=max(VALIDATION_YEARS),
        **SCALE_BB_CONFIG,
    )
    fit = fit_scale_bb(rates_train, ages=ages, years=years_train, config=cfg)
    fit = project_scale_bb(fit, base_year=TRAIN_CUTOFF)

    # Tidy fit table (observed + smoothed + projected)
    proj_years = fit.projection_years
    rate_proj = fit.rate_projected

    fit_rows = []
    # observed (training)
    for j, y in enumerate(years_train):
        for i, a in enumerate(ages):
            fit_rows.append({
                "disease": disease, "sex": sex,
                "age_low": int(a), "year": int(y),
                "kind": "observed_train",
                "rate_per_100k": float(rates_train[i, j])
                if np.isfinite(rates_train[i, j]) else np.nan,
            })
    # smoothed (training)
    for j, y in enumerate(years_train):
        for i, a in enumerate(ages):
            fit_rows.append({
                "disease": disease, "sex": sex,
                "age_low": int(a), "year": int(y),
                "kind": "smoothed",
                "rate_per_100k": float(fit.rate_smoothed[i, j]),
            })
    # projected (post-cutoff)
    for j, y in enumerate(proj_years):
        if y <= TRAIN_CUTOFF:
            continue
        for i, a in enumerate(ages):
            fit_rows.append({
                "disease": disease, "sex": sex,
                "age_low": int(a), "year": int(y),
                "kind": "projected",
                "rate_per_100k": float(rate_proj[i, j]),
            })
    fit_df = pd.DataFrame(fit_rows)

    # Validation table: project vs actual on 2015-2024
    val_rows = []
    actuals_all = df[
        (df["disease_id"] == disease)
        & (df["sex"] == sex)
        & (df["age_low"] >= AGE_MIN)
        & (df["age_low"] <= AGE_MAX)
        & (df["year"].isin(VALIDATION_YEARS))
    ]
    actual_piv = actuals_all.pivot_table(
        index="age_low", columns="year", values="rate_per_100k", aggfunc="mean"
    ).reindex(index=ages, columns=VALIDATION_YEARS)
    for j, y in enumerate(VALIDATION_YEARS):
        proj_idx = int(np.where(proj_years == y)[0][0]) if y in proj_years else None
        for i, a in enumerate(ages):
            actual = actual_piv.iloc[i, j]
            predicted = rate_proj[i, proj_idx] if proj_idx is not None else np.nan
            val_rows.append({
                "disease": disease, "sex": sex,
                "age_low": int(a), "year": int(y),
                "actual_rate_per_100k": float(actual) if pd.notna(actual) else np.nan,
                "predicted_rate_per_100k": float(predicted) if np.isfinite(predicted) else np.nan,
            })
    val_df = pd.DataFrame(val_rows)
    val_df["error"] = val_df["predicted_rate_per_100k"] - val_df["actual_rate_per_100k"]
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = val_df["error"] / val_df["actual_rate_per_100k"]
    # zero actual → undefined relative error; replace with NaN
    rel = rel.where(val_df["actual_rate_per_100k"] > 0, np.nan)
    val_df["rel_error"] = rel
    val_df["abs_rel_error"] = val_df["rel_error"].abs()

    return fit_df, val_df


def make_trajectory_plot(disease: str, sex: str, fit_df: pd.DataFrame, val_df: pd.DataFrame):
    if fit_df.empty:
        return
    # plot rates aggregated over selected age groups
    select_ages = [40, 60, 75]
    obs = fit_df[fit_df["kind"] == "observed_train"]
    sm = fit_df[fit_df["kind"] == "smoothed"]
    pr = fit_df[fit_df["kind"] == "projected"]
    fig, axes = plt.subplots(1, len(select_ages), figsize=(4.5 * len(select_ages), 4), sharey=False)
    if len(select_ages) == 1:
        axes = [axes]
    colors = {"obs": "#1f77b4", "sm": "#ff7f0e", "pr": "#2ca02c", "act": "#d62728"}
    for ax, a in zip(axes, select_ages):
        o = obs[obs["age_low"] == a].sort_values("year")
        s = sm[sm["age_low"] == a].sort_values("year")
        p = pr[pr["age_low"] == a].sort_values("year")
        v = val_df[val_df["age_low"] == a].sort_values("year")
        val_label = f"actual {VALIDATION_YEARS[0]}-{VALIDATION_YEARS[-1]}"
        ax.plot(o["year"], o["rate_per_100k"], "o-", color=colors["obs"],
                label=f"observed (≤{TRAIN_CUTOFF})", markersize=4)
        ax.plot(s["year"], s["rate_per_100k"], "-", color=colors["sm"],
                label="smoothed (Phase 1)", alpha=0.8)
        ax.plot(p["year"], p["rate_per_100k"], "--", color=colors["pr"],
                label="ScaleBB projection")
        ax.plot(v["year"], v["actual_rate_per_100k"], "x-", color=colors["act"],
                label=val_label, markersize=6)
        ax.set_title(f"age {a}-{a+4}")
        ax.set_xlabel("year")
        ax.set_ylabel("mortality rate (per 100k)")
        ax.set_yscale("log")
        ax.grid(alpha=0.3)
        ax.axvline(TRAIN_CUTOFF, color="grey", linestyle=":", alpha=0.6)
    axes[-1].legend(fontsize=8, loc="best")
    fig.suptitle(
        f"{disease} ({sex}) — train ≤{TRAIN_CUTOFF}, project & validate "
        f"{VALIDATION_YEARS[0]}-{VALIDATION_YEARS[-1]}",
        fontsize=11,
    )
    fig.tight_layout()
    out = OUT_FIGS / f"{disease}_{sex}_trajectory.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


def _safe_round(x, n=2):
    return round(x, n) if pd.notna(x) and np.isfinite(x) else np.nan


def make_overall_plots(per_year: pd.DataFrame):
    """Per-disease MAPE / bias trends over 2015-2024 (sex=total)."""
    sub = per_year[per_year["sex"] == "total"].copy()
    diseases = sorted(sub["disease"].unique())
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    cmap = plt.get_cmap("tab10")
    for i, d in enumerate(diseases):
        g = sub[sub["disease"] == d].sort_values("year")
        axes[0].plot(g["year"], g["MAPE_pct"], "o-", color=cmap(i % 10), label=d)
        axes[1].plot(g["year"], g["mean_rel_bias_pct"], "o-", color=cmap(i % 10), label=d)

    axes[0].set_title("MAPE by year (sex=total, ages 20-89)")
    axes[0].set_ylabel("MAPE %")
    axes[0].set_xlabel("year")
    axes[0].grid(alpha=0.3)
    axes[0].legend(fontsize=8, ncol=2)
    axes[1].set_title("Mean relative bias by year (predicted − actual, %)")
    axes[1].set_ylabel("rel bias %")
    axes[1].set_xlabel("year")
    axes[1].axhline(0, color="black", lw=0.6)
    axes[1].grid(alpha=0.3)
    axes[1].legend(fontsize=8, ncol=2)
    fig.suptitle(f"ScaleBB backtest accuracy by year (train ≤{TRAIN_CUTOFF})", fontsize=12)
    fig.tight_layout()
    out = OUT_FIGS / "overall_mape_bias_by_year.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print(f"wrote {out.name}")


def summarize(val_df: pd.DataFrame) -> pd.DataFrame:
    grp = val_df.dropna(subset=["actual_rate_per_100k", "predicted_rate_per_100k"]).groupby(
        ["disease", "sex"]
    )
    rows = []
    for (disease, sex), g in grp:
        g_pos = g[g["actual_rate_per_100k"] > 0]
        mape = g_pos["abs_rel_error"].mean() * 100 if len(g_pos) else np.nan
        rmse = np.sqrt(((g["predicted_rate_per_100k"] - g["actual_rate_per_100k"]) ** 2).mean())
        bias = g["error"].mean()
        rel_bias = g_pos["rel_error"].mean() * 100 if len(g_pos) else np.nan
        per_year_mape = g_pos.groupby("year")["abs_rel_error"].mean() * 100
        per_year_rmse = g.groupby("year").apply(
            lambda x: float(np.sqrt(((x["predicted_rate_per_100k"] - x["actual_rate_per_100k"]) ** 2).mean())),
            include_groups=False,
        )
        y_first = VALIDATION_YEARS[0]
        y_last = VALIDATION_YEARS[-1]
        y_mid = VALIDATION_YEARS[len(VALIDATION_YEARS) // 2]
        rows.append({
            "disease": disease, "sex": sex,
            "n_cells": len(g),
            "MAPE_pct": _safe_round(mape),
            "RMSE_per100k": _safe_round(rmse, 3),
            "bias_per100k": _safe_round(bias, 3),
            "mean_rel_bias_pct": _safe_round(rel_bias),
            f"MAPE_{y_first}": _safe_round(per_year_mape.get(y_first, np.nan)),
            f"MAPE_{y_mid}": _safe_round(per_year_mape.get(y_mid, np.nan)),
            f"MAPE_{y_last}": _safe_round(per_year_mape.get(y_last, np.nan)),
            f"RMSE_{y_first}": _safe_round(per_year_rmse.get(y_first, np.nan), 3),
            f"RMSE_{y_last}": _safe_round(per_year_rmse.get(y_last, np.nan), 3),
        })
    return pd.DataFrame(rows)


def summarize_per_year(val_df: pd.DataFrame) -> pd.DataFrame:
    """Per-disease/sex/year aggregated metrics for trend analysis."""
    rows = []
    for (disease, sex, year), g in val_df.dropna(
        subset=["actual_rate_per_100k", "predicted_rate_per_100k"]
    ).groupby(["disease", "sex", "year"]):
        g_pos = g[g["actual_rate_per_100k"] > 0]
        mape = g_pos["abs_rel_error"].mean() * 100 if len(g_pos) else np.nan
        rmse = float(np.sqrt(((g["predicted_rate_per_100k"] - g["actual_rate_per_100k"]) ** 2).mean()))
        bias = g["error"].mean()
        rel_bias = g_pos["rel_error"].mean() * 100 if len(g_pos) else np.nan
        rows.append({
            "disease": disease, "sex": sex, "year": int(year),
            "n_cells": len(g),
            "MAPE_pct": _safe_round(mape),
            "RMSE_per100k": _safe_round(rmse, 3),
            "bias_per100k": _safe_round(bias, 3),
            "mean_rel_bias_pct": _safe_round(rel_bias),
        })
    return pd.DataFrame(rows)


def _parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--train-cutoff", type=int, default=2014)
    p.add_argument("--validation-end", type=int, default=2024)
    p.add_argument("--output-subdir", type=str, default="",
                   help="subdir under output/ (e.g. 'cutoff_2021'). Empty = legacy location.")
    return p.parse_args()


def main():
    global TRAIN_CUTOFF, VALIDATION_YEARS, OUT_TABLES, OUT_FIGS
    args = _parse_args()
    TRAIN_CUTOFF = args.train_cutoff
    VALIDATION_YEARS = list(range(TRAIN_CUTOFF + 1, args.validation_end + 1))
    base = _paths.OUTPUT_DIR  # [REPRO] originally: ROOT/"BackTest_ScaleBB_2015_2024"/"output"
    if args.output_subdir:
        base = base / args.output_subdir
    OUT_TABLES = base / "tables"
    OUT_FIGS = base / "figures"
    OUT_TABLES.mkdir(parents=True, exist_ok=True)
    OUT_FIGS.mkdir(parents=True, exist_ok=True)

    print(f"train cutoff: {TRAIN_CUTOFF}, validate: {VALIDATION_YEARS}")
    print(f"output: {base}")
    panel = pd.read_csv(PANEL)
    diseases = sorted(panel["disease_id"].unique())
    sexes = ["total", "male", "female"]
    print(f"diseases: {diseases}")
    print(f"sexes: {sexes}")

    all_fit, all_val = [], []
    for disease in diseases:
        for sex in sexes:
            print(f"--- {disease}/{sex} ---")
            fit_df, val_df = run_one(panel, disease=disease, sex=sex)
            if fit_df.empty:
                print("  skipped (no data)")
                continue
            all_fit.append(fit_df)
            all_val.append(val_df)
            if sex == "total":
                fig_path = make_trajectory_plot(disease, sex, fit_df, val_df)
                print(f"  wrote {fig_path.name}")

    fit_long = pd.concat(all_fit, ignore_index=True)
    val_long = pd.concat(all_val, ignore_index=True)
    fit_long.to_csv(OUT_TABLES / "fit_long.csv", index=False)
    val_long.to_csv(OUT_TABLES / "validation_long.csv", index=False)
    print(f"wrote fit_long.csv ({len(fit_long):,} rows)")
    print(f"wrote validation_long.csv ({len(val_long):,} rows)")

    summary = summarize(val_long)
    summary = summary.sort_values(["disease", "sex"]).reset_index(drop=True)
    summary.to_csv(OUT_TABLES / "validation_summary.csv", index=False)
    print()
    print("=== validation summary ===")
    print(summary.to_string(index=False))

    per_year = summarize_per_year(val_long)
    per_year = per_year.sort_values(["disease", "sex", "year"]).reset_index(drop=True)
    per_year.to_csv(OUT_TABLES / "validation_by_year.csv", index=False)
    print()
    print(f"wrote validation_by_year.csv ({len(per_year):,} rows)")

    make_overall_plots(per_year)


if __name__ == "__main__":
    main()
