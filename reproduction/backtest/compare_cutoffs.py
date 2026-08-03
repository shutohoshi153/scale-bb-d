"""Cross-cutoff comparison: 2014 vs 2021 vs 2022 training cutoff.

Reads validation_summary.csv and method_comparison_MAPE_wide.csv from each
run (cutoff=2014 lives under output/, others under output/cutoff_<yr>/) and
produces side-by-side comparison tables + figures.

Output:
  output/cutoff_comparison/tables/scalebb_cutoff_comparison.csv
  output/cutoff_comparison/tables/method_cutoff_comparison.csv
  output/cutoff_comparison/figures/scalebb_cutoff_comparison.png
  output/cutoff_comparison/figures/method_cutoff_comparison.png
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
OUT = BASE / "cutoff_comparison"
(OUT / "tables").mkdir(parents=True, exist_ok=True)
(OUT / "figures").mkdir(parents=True, exist_ok=True)


CUTOFFS = [
    (2014, None, "train ≤2014 → validate 2015-2024"),
    (2021, "cutoff_2021", "train ≤2021 → validate 2022-2024"),
    (2022, "cutoff_2022", "train ≤2022 → validate 2023-2024"),
]
KEEP = ["MAPE_pct", "RMSE_per100k", "bias_per100k", "mean_rel_bias_pct"]


def load_scalebb(cutoff_subdir: str | None) -> pd.DataFrame:
    p = BASE / cutoff_subdir / "tables" / "validation_summary.csv" if cutoff_subdir else BASE / "tables" / "validation_summary.csv"
    df = pd.read_csv(p)
    return df[["disease", "sex"] + KEEP]


def load_wide(cutoff_subdir: str | None) -> pd.DataFrame:
    p = BASE / cutoff_subdir / "tables" / "method_comparison_MAPE_wide.csv" if cutoff_subdir else BASE / "tables" / "method_comparison_MAPE_wide.csv"
    return pd.read_csv(p)


def main():
    sb_frames = []
    for cutoff, subdir, _ in CUTOFFS:
        df = load_scalebb(subdir).rename(columns={c: f"{c}_{cutoff}" for c in KEEP})
        sb_frames.append(df)
    sb = sb_frames[0]
    for f in sb_frames[1:]:
        sb = sb.merge(f, on=["disease", "sex"])
    sb["delta_MAPE_2021_vs_2014"] = sb["MAPE_pct_2021"] - sb["MAPE_pct_2014"]
    sb["delta_MAPE_2022_vs_2014"] = sb["MAPE_pct_2022"] - sb["MAPE_pct_2014"]
    sb["delta_MAPE_2022_vs_2021"] = sb["MAPE_pct_2022"] - sb["MAPE_pct_2021"]
    sb = sb.sort_values(["sex", "disease"]).reset_index(drop=True)
    out_sb = OUT / "tables" / "scalebb_cutoff_comparison.csv"
    sb.to_csv(out_sb, index=False)
    print(f"wrote {out_sb} ({len(sb)} rows)")
    print()
    print("=== ScaleBB cutoff comparison (sex=total) ===")
    cols = ["disease", "MAPE_pct_2014", "MAPE_pct_2021", "MAPE_pct_2022",
            "bias_per100k_2014", "bias_per100k_2021", "bias_per100k_2022"]
    print(sb[sb["sex"] == "total"][cols].to_string(index=False))

    # All-methods cutoff comparison (long format)
    method_frames = []
    for cutoff, subdir, _ in CUTOFFS:
        w = load_wide(subdir)
        long = w.melt(id_vars=["disease", "sex"],
                      value_vars=["scalebb", "naive_last", "mean_3pts", "loglin_trend"],
                      var_name="method", value_name=f"MAPE_{cutoff}")
        method_frames.append(long)
    m = method_frames[0]
    for f in method_frames[1:]:
        m = m.merge(f, on=["disease", "sex", "method"])
    m["delta_2021_vs_2014"] = m["MAPE_2021"] - m["MAPE_2014"]
    m["delta_2022_vs_2021"] = m["MAPE_2022"] - m["MAPE_2021"]
    m = m.sort_values(["sex", "disease", "method"]).reset_index(drop=True)
    out_m = OUT / "tables" / "method_cutoff_comparison.csv"
    m.to_csv(out_m, index=False)
    print(f"\nwrote {out_m} ({len(m)} rows)")

    # Plot 1: ScaleBB bar comparison sex=total (3 cutoffs)
    sub = sb[sb["sex"] == "total"].sort_values("MAPE_pct_2014")
    diseases = sub["disease"].tolist()
    x = np.arange(len(diseases))
    w = 0.25
    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.bar(x - w, sub["MAPE_pct_2014"], width=w, color="#d62728", label=CUTOFFS[0][2])
    ax.bar(x, sub["MAPE_pct_2021"], width=w, color="#ff7f0e", label=CUTOFFS[1][2])
    ax.bar(x + w, sub["MAPE_pct_2022"], width=w, color="#2ca02c", label=CUTOFFS[2][2])
    ax.set_xticks(x)
    ax.set_xticklabels(diseases, rotation=20, ha="right")
    ax.set_ylabel("ScaleBB MAPE %")
    ax.set_title("ScaleBB accuracy by training cutoff (sex=total)")
    ax.grid(axis="y", alpha=0.3)
    ax.legend(fontsize=9)
    fig.tight_layout()
    out_fig = OUT / "figures" / "scalebb_cutoff_comparison.png"
    fig.savefig(out_fig, dpi=120)
    plt.close(fig)
    print(f"wrote {out_fig.name}")

    # Plot 2: 4 methods × 3 cutoffs (faceted)
    sub_tot = m[m["sex"] == "total"].copy()
    diseases = sorted(sub_tot["disease"].unique())
    methods = ["scalebb", "naive_last", "mean_3pts", "loglin_trend"]
    colors = {"scalebb": "#2ca02c", "naive_last": "#1f77b4", "mean_3pts": "#ff7f0e", "loglin_trend": "#d62728"}
    fig, axes = plt.subplots(1, 3, figsize=(20, 5.5), sharey=True)
    for ax, (cutoff, _, title) in zip(axes, CUTOFFS):
        col = f"MAPE_{cutoff}"
        x = np.arange(len(diseases))
        w = 0.2
        for k, meth in enumerate(methods):
            vals = []
            for d in diseases:
                row = sub_tot[(sub_tot["disease"] == d) & (sub_tot["method"] == meth)]
                vals.append(row[col].iloc[0] if not row.empty else 0)
            ax.bar(x + (k - 1.5) * w, vals, width=w, color=colors[meth], label=meth)
        ax.set_xticks(x)
        ax.set_xticklabels(diseases, rotation=25, ha="right")
        ax.set_title(title)
        ax.grid(axis="y", alpha=0.3)
        ax.set_ylabel("MAPE %")
    axes[0].legend(fontsize=9)
    fig.suptitle("MAPE by method × disease × training cutoff (sex=total)", fontsize=12)
    fig.tight_layout()
    out_fig2 = OUT / "figures" / "method_cutoff_comparison.png"
    fig.savefig(out_fig2, dpi=120)
    plt.close(fig)
    print(f"wrote {out_fig2.name}")

    # Plot 3: ScaleBB - best_baseline gap (positive = scalebb worse)
    gap_rows = []
    for cutoff, _, _ in [(c, s, t) for (c, s, t) in CUTOFFS]:
        col = f"MAPE_{cutoff}"
        for d in diseases:
            sub_d = sub_tot[sub_tot["disease"] == d]
            scalebb_val = sub_d[sub_d["method"] == "scalebb"][col].iloc[0]
            base_vals = sub_d[sub_d["method"] != "scalebb"][col]
            best_base = base_vals.min()
            gap_rows.append({"cutoff": cutoff, "disease": d, "gap_pp": scalebb_val - best_base})
    gap_df = pd.DataFrame(gap_rows)
    gap_df.to_csv(OUT / "tables" / "scalebb_minus_best_baseline_gap.csv", index=False)
    fig, ax = plt.subplots(figsize=(11, 5))
    x = np.arange(len(diseases))
    w = 0.25
    for k, (cutoff, _, _) in enumerate(CUTOFFS):
        vals = [gap_df[(gap_df["cutoff"] == cutoff) & (gap_df["disease"] == d)]["gap_pp"].iloc[0] for d in diseases]
        color = ["#d62728", "#ff7f0e", "#2ca02c"][k]
        ax.bar(x + (k - 1) * w, vals, width=w, color=color, label=f"cutoff {cutoff}")
    ax.axhline(0, color="black", lw=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels(diseases, rotation=20, ha="right")
    ax.set_ylabel("ScaleBB MAPE − best baseline MAPE (pp)")
    ax.set_title("ScaleBB disadvantage vs best baseline (positive = ScaleBB worse)")
    ax.grid(axis="y", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    out_fig3 = OUT / "figures" / "scalebb_gap_vs_best_baseline.png"
    fig.savefig(out_fig3, dpi=120)
    plt.close(fig)
    print(f"wrote {out_fig3.name}")


if __name__ == "__main__":
    main()
