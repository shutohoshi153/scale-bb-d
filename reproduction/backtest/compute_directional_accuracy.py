"""Directional accuracy: did the method predict the correct sign of change
relative to the observed rate at the training cutoff?

For each (disease, sex, age, year):
  actual_change    = actual_rate    - rate_at_cutoff
  predicted_change = predicted_rate - rate_at_cutoff
  match = sign(actual_change) == sign(predicted_change), excluding cells
          where sign(actual_change) == 0 (ambiguous truth).

Cells where the method predicts no change (sign(predicted_change) == 0,
e.g. naive_last by construction) count as a miss — that is the point: such
methods carry no directional signal.

Outputs (under output/directional/):
  tables/directional_long.csv             cell-level rows with match flag
  tables/directional_summary.csv          per (cutoff, method, disease, sex)
  tables/directional_summary_total.csv    same, sex=total only (wide-friendly)
  figures/scalebb_directional_per_cutoff.png   bar: ScaleBB per disease × cutoff
  figures/method_directional_comparison.png    grouped bar: 4 methods × disease, 3 panels
  figures/scalebb_vs_loglin_directional.png    head-to-head ScaleBB vs loglin_trend
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# [REPRO] Paths consolidated in the self-contained path layer
# (originally: relative references from ROOT=parents[2])
import _paths

BASE = _paths.OUTPUT_DIR  # originally: ROOT/"BackTest_ScaleBB_2015_2024"/"output"
OUT = BASE / "directional"
(OUT / "tables").mkdir(parents=True, exist_ok=True)
(OUT / "figures").mkdir(parents=True, exist_ok=True)

CUTOFFS = [
    (2014, None,           "train ≤2014 → 2015-2024"),
    (2021, "cutoff_2021",  "train ≤2021 → 2022-2024"),
    (2022, "cutoff_2022",  "train ≤2022 → 2023-2024"),
]


def _base_dir(subdir: str | None) -> Path:
    return BASE / subdir if subdir else BASE


def load_observed_at_cutoff(subdir: str | None, cutoff: int) -> pd.DataFrame:
    fit = pd.read_csv(_base_dir(subdir) / "tables" / "fit_long.csv")
    o = fit[(fit["kind"] == "observed_train") & (fit["year"] == cutoff)].copy()
    return o[["disease", "sex", "age_low", "rate_per_100k"]].rename(
        columns={"rate_per_100k": "rate_at_cutoff"}
    )


def load_val(subdir: str | None) -> pd.DataFrame:
    sb = pd.read_csv(_base_dir(subdir) / "tables" / "validation_long.csv")
    sb = sb[["disease", "sex", "age_low", "year",
             "actual_rate_per_100k", "predicted_rate_per_100k"]].copy()
    sb["method"] = "scalebb"

    base = pd.read_csv(_base_dir(subdir) / "tables" / "validation_long_baseline.csv")
    base = base[["method", "disease", "sex", "age_low", "year",
                 "actual_rate_per_100k", "predicted_rate_per_100k"]].copy()

    return pd.concat([sb, base], ignore_index=True)


def compute_directional(cutoff: int, subdir: str | None) -> pd.DataFrame:
    obs = load_observed_at_cutoff(subdir, cutoff)
    val = load_val(subdir)
    df = val.merge(obs, on=["disease", "sex", "age_low"], how="left")
    df["actual_change"] = df["actual_rate_per_100k"] - df["rate_at_cutoff"]
    df["predicted_change"] = df["predicted_rate_per_100k"] - df["rate_at_cutoff"]
    df = df.dropna(subset=["actual_change", "predicted_change", "rate_at_cutoff"])
    df["actual_sign"] = np.sign(df["actual_change"])
    df["pred_sign"] = np.sign(df["predicted_change"])
    df["match"] = (df["actual_sign"] == df["pred_sign"]) & (df["actual_sign"] != 0)
    df["evaluable"] = df["actual_sign"] != 0  # exclude ambiguous-truth cells
    df["cutoff"] = cutoff
    return df


def summarize(long_df: pd.DataFrame) -> pd.DataFrame:
    evl = long_df[long_df["evaluable"]]
    grp = evl.groupby(["cutoff", "method", "disease", "sex"])
    rows = []
    for (cutoff, method, disease, sex), g in grp:
        n = len(g)
        matches = int(g["match"].sum())
        # share of predictions that are "no change" (signal-less)
        n_flat = int((g["pred_sign"] == 0).sum())
        rows.append({
            "cutoff": cutoff, "method": method, "disease": disease, "sex": sex,
            "n_cells_evaluable": n,
            "n_matches": matches,
            "dir_acc_pct": round(matches / n * 100, 2) if n else np.nan,
            "n_flat_preds": n_flat,
            "flat_pred_pct": round(n_flat / n * 100, 2) if n else np.nan,
        })
    return pd.DataFrame(rows)


def main():
    all_long = []
    for cutoff, subdir, _ in CUTOFFS:
        long_df = compute_directional(cutoff, subdir)
        all_long.append(long_df)
    long_all = pd.concat(all_long, ignore_index=True)
    long_all.to_csv(OUT / "tables" / "directional_long.csv", index=False)
    print(f"wrote directional_long.csv ({len(long_all):,} rows)")

    summary = summarize(long_all)
    summary = summary.sort_values(["cutoff", "method", "disease", "sex"]).reset_index(drop=True)
    summary.to_csv(OUT / "tables" / "directional_summary.csv", index=False)
    print(f"wrote directional_summary.csv ({len(summary)} rows)")

    summary_total = summary[summary["sex"] == "total"].copy()
    summary_total.to_csv(OUT / "tables" / "directional_summary_total.csv", index=False)

    # ---------- Plot 1: ScaleBB directional accuracy per cutoff ----------
    sb = summary_total[summary_total["method"] == "scalebb"].copy()
    diseases = sorted(sb["disease"].unique())
    x = np.arange(len(diseases))
    w = 0.25
    fig, ax = plt.subplots(figsize=(11, 5.5))
    colors = ["#d62728", "#ff7f0e", "#2ca02c"]
    for k, (cutoff, _, title) in enumerate(CUTOFFS):
        vals = []
        for d in diseases:
            row = sb[(sb["cutoff"] == cutoff) & (sb["disease"] == d)]
            vals.append(row["dir_acc_pct"].iloc[0] if not row.empty else 0)
        ax.bar(x + (k - 1) * w, vals, width=w, color=colors[k], label=title)
    ax.axhline(50, color="grey", lw=0.8, ls="--", alpha=0.7, label="coin flip (50%)")
    ax.set_xticks(x)
    ax.set_xticklabels(diseases, rotation=20, ha="right")
    ax.set_ylabel("Directional accuracy %  (higher = better)")
    ax.set_ylim(0, 100)
    ax.set_title("ScaleBB directional accuracy by training cutoff (sex=total)")
    ax.grid(axis="y", alpha=0.3)
    ax.legend(fontsize=9, loc="lower left")
    fig.tight_layout()
    out1 = OUT / "figures" / "scalebb_directional_per_cutoff.png"
    fig.savefig(out1, dpi=120)
    plt.close(fig)
    print(f"wrote {out1.name}")

    # ---------- Plot 2: 4 methods × 8 diseases × 3 cutoffs (3 panels) ----------
    methods = ["scalebb", "naive_last", "mean_3pts", "loglin_trend"]
    cmap = {"scalebb": "#2ca02c", "naive_last": "#1f77b4",
            "mean_3pts": "#ff7f0e", "loglin_trend": "#d62728"}
    fig, axes = plt.subplots(1, 3, figsize=(20, 5.5), sharey=True)
    for ax, (cutoff, _, title) in zip(axes, CUTOFFS):
        x = np.arange(len(diseases))
        w = 0.2
        for k, m in enumerate(methods):
            vals = []
            for d in diseases:
                row = summary_total[(summary_total["cutoff"] == cutoff)
                                    & (summary_total["disease"] == d)
                                    & (summary_total["method"] == m)]
                vals.append(row["dir_acc_pct"].iloc[0] if not row.empty else 0)
            ax.bar(x + (k - 1.5) * w, vals, width=w, color=cmap[m], label=m)
        ax.axhline(50, color="grey", lw=0.8, ls="--", alpha=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels(diseases, rotation=25, ha="right")
        ax.set_title(title)
        ax.set_ylabel("Directional accuracy %")
        ax.set_ylim(0, 100)
        ax.grid(axis="y", alpha=0.3)
    axes[0].legend(fontsize=9, loc="lower left")
    fig.suptitle(
        "Directional accuracy by method × disease × training cutoff (sex=total)\n"
        "naive_last predicts no change (pred_sign=0) by construction → directional accuracy = 0%",
        fontsize=11,
    )
    fig.tight_layout()
    out2 = OUT / "figures" / "method_directional_comparison.png"
    fig.savefig(out2, dpi=120)
    plt.close(fig)
    print(f"wrote {out2.name}")

    # ---------- Plot 3: head-to-head ScaleBB vs loglin_trend ----------
    # loglin_trend is the strongest baseline w/ explicit directional signal;
    # naive_last/mean_3pts have weak/no signal so a fair comparison is vs loglin.
    fig, axes = plt.subplots(1, 3, figsize=(20, 5.5), sharey=True)
    for ax, (cutoff, _, title) in zip(axes, CUTOFFS):
        x = np.arange(len(diseases))
        w = 0.4
        sb_vals, ll_vals = [], []
        for d in diseases:
            sb_row = summary_total[(summary_total["cutoff"] == cutoff)
                                   & (summary_total["disease"] == d)
                                   & (summary_total["method"] == "scalebb")]
            ll_row = summary_total[(summary_total["cutoff"] == cutoff)
                                   & (summary_total["disease"] == d)
                                   & (summary_total["method"] == "loglin_trend")]
            sb_vals.append(sb_row["dir_acc_pct"].iloc[0] if not sb_row.empty else 0)
            ll_vals.append(ll_row["dir_acc_pct"].iloc[0] if not ll_row.empty else 0)
        ax.bar(x - w / 2, sb_vals, width=w, color=cmap["scalebb"], label="scalebb")
        ax.bar(x + w / 2, ll_vals, width=w, color=cmap["loglin_trend"], label="loglin_trend")
        ax.axhline(50, color="grey", lw=0.8, ls="--", alpha=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels(diseases, rotation=25, ha="right")
        ax.set_title(title)
        ax.set_ylabel("Directional accuracy %")
        ax.set_ylim(0, 100)
        ax.grid(axis="y", alpha=0.3)
    axes[0].legend(fontsize=10, loc="lower left")
    fig.suptitle(
        "ScaleBB vs loglin_trend — directional accuracy head-to-head (sex=total)",
        fontsize=12,
    )
    fig.tight_layout()
    out3 = OUT / "figures" / "scalebb_vs_loglin_directional.png"
    fig.savefig(out3, dpi=120)
    plt.close(fig)
    print(f"wrote {out3.name}")

    # ---------- Print summary table ----------
    print()
    print("=== Directional accuracy (sex=total, all cutoffs) ===")
    pv = summary_total.pivot_table(
        index=["disease"], columns=["cutoff", "method"],
        values="dir_acc_pct", aggfunc="first",
    )
    print(pv.to_string())


if __name__ == "__main__":
    main()
