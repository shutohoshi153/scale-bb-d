"""Non-ScaleBB baselines for the same backtest setup.

Three baselines per disease/sex/age:
  - naive_last     : predicted_t = observed_(TRAIN_CUTOFF)
  - mean_3pts      : predicted_t = mean of last 3 observation points
  - loglin_trend   : OLS on log(rate) vs year over (TRAIN_CUTOFF-14 .. TRAIN_CUTOFF),
                     extrapolate forward (15-year trend window)

CLI args (all optional, defaults reproduce the original 2014/2024 run):
  --train-cutoff INT     last year used for training (default 2014)
  --validation-end INT   last year of validation window (default 2024)
  --output-subdir STR    subdir under output/ (default '' = legacy location)
  --trend-window INT     # of years before cutoff to use for loglin_trend (default 15)

Outputs (under output[/<subdir>]/tables/):
  validation_long_baseline.csv      tidy predicted vs actual per method
  validation_summary_baseline.csv   per (method, disease, sex) MAPE/RMSE/bias
  method_comparison_summary.csv     ScaleBB vs each baseline, with delta
  method_comparison_MAPE_wide.csv   pivoted MAPE per (disease, sex) × method
  method_comparison_by_year.csv     same broken down by year (sex=total)

Plus output/figures/baseline_vs_scalebb_mape.png + method_comparison_by_year.png.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# [REPRO] Paths consolidated in the self-contained path layer
# (originally: relative references from ROOT=parents[2])
import _paths

PANEL = _paths.PANEL
AGE_MIN, AGE_MAX = 20, 89

# Mutable globals — set in main() from CLI args. Defaults reproduce the original run.
TRAIN_CUTOFF: int = 2014
VALIDATION_YEARS: list[int] = list(range(2015, 2025))
TREND_WINDOW_START: int = 2000  # years used for log-linear fit
TABLES: Path = _paths.OUTPUT_DIR / "tables"
FIGS: Path = _paths.OUTPUT_DIR / "figures"


def predict_naive_last(years_train, rates_train):
    last_idx = int(np.argmax(years_train))
    return rates_train[:, last_idx]


def predict_mean_3pts(years_train, rates_train):
    # take the three latest observation points (e.g., 2010, 2013, 2014)
    order = np.argsort(years_train)[-3:]
    return np.nanmean(rates_train[:, order], axis=1)


def predict_loglin(years_train, rates_train, *, window_start: int | None = None):
    """OLS log(rate) ~ a + b*year per age, fitted on years >= window_start.

    Returns (intercept, slope) arrays of shape (n_age,).
    """
    if window_start is None:
        window_start = TREND_WINDOW_START
    mask = years_train >= window_start
    yrs = years_train[mask].astype(float)
    rt = rates_train[:, mask]
    n_age = rt.shape[0]
    a = np.full(n_age, np.nan)
    b = np.full(n_age, np.nan)
    for i in range(n_age):
        r = rt[i, :]
        ok = np.isfinite(r) & (r > 0)
        if ok.sum() < 3:
            continue
        x = yrs[ok]
        y = np.log(r[ok])
        # simple OLS
        x_mean = x.mean()
        y_mean = y.mean()
        denom = ((x - x_mean) ** 2).sum()
        if denom == 0:
            continue
        slope = ((x - x_mean) * (y - y_mean)).sum() / denom
        intercept = y_mean - slope * x_mean
        a[i] = intercept
        b[i] = slope
    return a, b


def build_panel_for(df, *, disease, sex):
    sub = df[
        (df["disease_id"] == disease)
        & (df["sex"] == sex)
        & (df["age_low"] >= AGE_MIN)
        & (df["age_low"] <= AGE_MAX)
    ]
    train = sub[sub["year"] <= TRAIN_CUTOFF]
    val = sub[sub["year"].isin(VALIDATION_YEARS)]
    train_piv = train.pivot_table(
        index="age_low", columns="year", values="rate_per_100k", aggfunc="mean"
    ).sort_index()
    val_piv = val.pivot_table(
        index="age_low", columns="year", values="rate_per_100k", aggfunc="mean"
    ).reindex(index=train_piv.index, columns=VALIDATION_YEARS)
    return (
        train_piv.index.to_numpy(dtype=int),
        train_piv.columns.to_numpy(dtype=int),
        train_piv.to_numpy(dtype=float),
        val_piv.to_numpy(dtype=float),
    )


def make_validation_rows(method, disease, sex, ages, val_actual, predicted_per_year):
    """predicted_per_year: (n_age, n_validation_years) array."""
    rows = []
    for j, y in enumerate(VALIDATION_YEARS):
        for i, a in enumerate(ages):
            rows.append({
                "method": method, "disease": disease, "sex": sex,
                "age_low": int(a), "year": int(y),
                "actual_rate_per_100k": float(val_actual[i, j])
                if np.isfinite(val_actual[i, j]) else np.nan,
                "predicted_rate_per_100k": float(predicted_per_year[i, j])
                if np.isfinite(predicted_per_year[i, j]) else np.nan,
            })
    return rows


def run_baselines_for(df, *, disease, sex):
    ages, years_train, rates_train, val_actual = build_panel_for(df, disease=disease, sex=sex)

    # naive last
    pred_last = predict_naive_last(years_train, rates_train)
    pred_last_year = np.tile(pred_last[:, None], (1, len(VALIDATION_YEARS)))

    # mean 3pts
    pred_mean = predict_mean_3pts(years_train, rates_train)
    pred_mean_year = np.tile(pred_mean[:, None], (1, len(VALIDATION_YEARS)))

    # loglin trend
    a, b = predict_loglin(years_train, rates_train)
    yrs = np.array(VALIDATION_YEARS, dtype=float)
    pred_loglin = np.exp(a[:, None] + b[:, None] * yrs[None, :])  # broadcasting

    rows = []
    rows += make_validation_rows("naive_last", disease, sex, ages, val_actual, pred_last_year)
    rows += make_validation_rows("mean_3pts", disease, sex, ages, val_actual, pred_mean_year)
    rows += make_validation_rows("loglin_trend", disease, sex, ages, val_actual, pred_loglin)
    return rows


def _safe_round(x, n=2):
    return round(x, n) if pd.notna(x) and np.isfinite(x) else np.nan


def summarize(val_df):
    val_df = val_df.copy()
    val_df["error"] = val_df["predicted_rate_per_100k"] - val_df["actual_rate_per_100k"]
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = val_df["error"] / val_df["actual_rate_per_100k"]
    rel = rel.where(val_df["actual_rate_per_100k"] > 0, np.nan)
    val_df["rel_error"] = rel
    val_df["abs_rel_error"] = val_df["rel_error"].abs()

    grp = val_df.dropna(subset=["actual_rate_per_100k", "predicted_rate_per_100k"]).groupby(
        ["method", "disease", "sex"]
    )
    rows = []
    for (method, disease, sex), g in grp:
        g_pos = g[g["actual_rate_per_100k"] > 0]
        mape = g_pos["abs_rel_error"].mean() * 100 if len(g_pos) else np.nan
        rmse = float(np.sqrt(((g["predicted_rate_per_100k"] - g["actual_rate_per_100k"]) ** 2).mean()))
        bias = g["error"].mean()
        rel_bias = g_pos["rel_error"].mean() * 100 if len(g_pos) else np.nan
        rows.append({
            "method": method, "disease": disease, "sex": sex,
            "n_cells": len(g),
            "MAPE_pct": _safe_round(mape),
            "RMSE_per100k": _safe_round(rmse, 3),
            "bias_per100k": _safe_round(bias, 3),
            "mean_rel_bias_pct": _safe_round(rel_bias),
        })
    return pd.DataFrame(rows), val_df


def _parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--train-cutoff", type=int, default=2014)
    p.add_argument("--validation-end", type=int, default=2024)
    p.add_argument("--output-subdir", type=str, default="")
    p.add_argument("--trend-window", type=int, default=15,
                   help="# years (cutoff inclusive) used for loglin_trend fit")
    return p.parse_args()


def main():
    global TRAIN_CUTOFF, VALIDATION_YEARS, TREND_WINDOW_START, TABLES, FIGS
    args = _parse_args()
    TRAIN_CUTOFF = args.train_cutoff
    VALIDATION_YEARS = list(range(TRAIN_CUTOFF + 1, args.validation_end + 1))
    TREND_WINDOW_START = TRAIN_CUTOFF - args.trend_window + 1
    base = _paths.OUTPUT_DIR  # [REPRO] originally: ROOT/"BackTest_ScaleBB_2015_2024"/"output"
    if args.output_subdir:
        base = base / args.output_subdir
    TABLES = base / "tables"
    FIGS = base / "figures"
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGS.mkdir(parents=True, exist_ok=True)

    print(f"train cutoff: {TRAIN_CUTOFF}, validate: {VALIDATION_YEARS}")
    print(f"loglin trend window: {TREND_WINDOW_START}..{TRAIN_CUTOFF}")
    print(f"output: {base}")

    panel = pd.read_csv(PANEL)
    diseases = sorted(panel["disease_id"].unique())
    sexes = ["total", "male", "female"]

    all_rows = []
    for disease in diseases:
        for sex in sexes:
            all_rows += run_baselines_for(panel, disease=disease, sex=sex)

    val_df = pd.DataFrame(all_rows)
    summary, val_df_enriched = summarize(val_df)
    val_df_enriched.to_csv(TABLES / "validation_long_baseline.csv", index=False)
    summary = summary.sort_values(["disease", "sex", "method"]).reset_index(drop=True)
    summary.to_csv(TABLES / "validation_summary_baseline.csv", index=False)
    print(f"wrote validation_long_baseline.csv ({len(val_df_enriched):,} rows)")
    print(f"wrote validation_summary_baseline.csv ({len(summary)} rows)")

    # Merge with ScaleBB results
    scalebb = pd.read_csv(TABLES / "validation_summary.csv")
    scalebb = scalebb[["disease", "sex", "MAPE_pct", "RMSE_per100k", "bias_per100k", "mean_rel_bias_pct"]].copy()
    scalebb["method"] = "scalebb"
    base = summary[["method", "disease", "sex", "MAPE_pct", "RMSE_per100k", "bias_per100k", "mean_rel_bias_pct"]]
    methods_all = pd.concat([scalebb, base], ignore_index=True)
    methods_all = methods_all.sort_values(["disease", "sex", "method"]).reset_index(drop=True)
    methods_all.to_csv(TABLES / "method_comparison_summary.csv", index=False)
    print(f"wrote method_comparison_summary.csv ({len(methods_all)} rows)")

    # Wide table: per (disease, sex), MAPE for each method + delta vs scalebb
    wide = methods_all.pivot_table(
        index=["disease", "sex"], columns="method",
        values="MAPE_pct", aggfunc="first",
    ).reset_index()
    for m in ["naive_last", "mean_3pts", "loglin_trend"]:
        if m in wide.columns:
            wide[f"delta_{m}_minus_scalebb"] = wide[m] - wide["scalebb"]
    wide = wide.sort_values(["sex", "disease"]).reset_index(drop=True)
    wide.to_csv(TABLES / "method_comparison_MAPE_wide.csv", index=False)
    print(f"wrote method_comparison_MAPE_wide.csv ({len(wide)} rows)")

    # Per-year per-method MAPE for sex=total
    by_year_rows = []
    for method, g in val_df_enriched[val_df_enriched["sex"] == "total"].groupby("method"):
        for (disease, year), gg in g.groupby(["disease", "year"]):
            gg_pos = gg[gg["actual_rate_per_100k"] > 0]
            mape = gg_pos["abs_rel_error"].mean() * 100 if len(gg_pos) else np.nan
            by_year_rows.append({
                "method": method, "disease": disease, "year": int(year),
                "MAPE_pct": _safe_round(mape),
            })
    # also include ScaleBB
    scalebb_by_year = pd.read_csv(TABLES / "validation_by_year.csv")
    scalebb_by_year = scalebb_by_year[scalebb_by_year["sex"] == "total"][["disease", "year", "MAPE_pct"]].copy()
    scalebb_by_year["method"] = "scalebb"
    by_year_df = pd.concat([pd.DataFrame(by_year_rows), scalebb_by_year], ignore_index=True)
    by_year_df = by_year_df.sort_values(["disease", "method", "year"]).reset_index(drop=True)
    by_year_df.to_csv(TABLES / "method_comparison_by_year.csv", index=False)
    print(f"wrote method_comparison_by_year.csv ({len(by_year_df)} rows)")

    # Plot: per-disease MAPE bar comparison (sex=total)
    sub = wide[wide["sex"] == "total"].copy()
    diseases_order = sub.sort_values("scalebb")["disease"].tolist()
    fig, ax = plt.subplots(figsize=(11, 5.5))
    x = np.arange(len(diseases_order))
    w = 0.2
    methods = ["scalebb", "naive_last", "mean_3pts", "loglin_trend"]
    colors = {"scalebb": "#2ca02c", "naive_last": "#1f77b4", "mean_3pts": "#ff7f0e", "loglin_trend": "#d62728"}
    for k, m in enumerate(methods):
        vals = [sub.loc[sub["disease"] == d, m].iloc[0] if not sub.loc[sub["disease"] == d, m].empty else 0 for d in diseases_order]
        ax.bar(x + (k - 1.5) * w, vals, width=w, color=colors[m], label=m)
    ax.set_xticks(x)
    ax.set_xticklabels(diseases_order, rotation=30, ha="right")
    ax.set_ylabel(f"MAPE % (sex=total, {VALIDATION_YEARS[0]}-{VALIDATION_YEARS[-1]})")
    ax.set_title(
        f"Backtest MAPE by method — lower is better  (train ≤{TRAIN_CUTOFF})"
    )
    ax.grid(axis="y", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    out = FIGS / "baseline_vs_scalebb_mape.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print(f"wrote {out.name}")

    # Per-year MAPE trend per disease (3 panels by method)
    fig, axes = plt.subplots(2, 4, figsize=(16, 8), sharex=True)
    axes = axes.flatten()
    cmap = {"scalebb": "#2ca02c", "naive_last": "#1f77b4", "mean_3pts": "#ff7f0e", "loglin_trend": "#d62728"}
    for ax, disease in zip(axes, sorted(by_year_df["disease"].unique())):
        for method, g in by_year_df[by_year_df["disease"] == disease].groupby("method"):
            ax.plot(g["year"], g["MAPE_pct"], "o-", color=cmap.get(method, "k"), label=method, markersize=4)
        ax.set_title(disease)
        ax.set_xlabel("year")
        ax.set_ylabel("MAPE %")
        ax.grid(alpha=0.3)
    axes[0].legend(fontsize=8)
    fig.suptitle(f"MAPE by year, all methods (sex=total, train ≤{TRAIN_CUTOFF})")
    fig.tight_layout()
    out2 = FIGS / "method_comparison_by_year.png"
    fig.savefig(out2, dpi=120)
    plt.close(fig)
    print(f"wrote {out2.name}")

    # Print the comparison table
    print()
    print("=== MAPE wide (sex=total) ===")
    print(wide[wide["sex"] == "total"].to_string(index=False))


if __name__ == "__main__":
    main()
