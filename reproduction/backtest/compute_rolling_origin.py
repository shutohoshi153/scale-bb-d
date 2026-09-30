"""Rolling-origin robustness check (paper §4.2 / §6.2, added 2026-09-02).

Re-uses the directional-accuracy definition of compute_directional_accuracy.py
for every training cutoff 2014, 2015, ..., 2022 (validation = cutoff+1 .. 2024)
and reports, per disease (sex=total):

  * DA of Scale BB-D, loglin_trend and the two reference baselines
    (always_down, sign_last_change), plus the majority-direction share
  * Scale BB-D MAPE gap to the best baseline [pp]

The point of the exercise: the 3-cutoff design (2014 / 2021 / 2022) places the
pre-shock cutoff five years before the break.  Cutoffs 2015-2019 show how the
directional result depends on how many pre-shock years precede the validation
window, and cutoff 2019 is the case where the validation window *is* the shock.

Inputs : output/ (cutoff 2014) and output/cutoff_<y>/ for y = 2015..2022
         (produced by run_backtest.py / run_baselines.py, see run_all.sh)
Outputs: output/directional/tables/rolling_origin_da.csv
         output/directional/tables/rolling_origin_mape_gap.csv
         output/directional/figures/rolling_origin_da_heatmap.png
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import _paths
import compute_directional_accuracy as cda

BASE = _paths.OUTPUT_DIR
OUT = BASE / "directional"
CUTOFFS = list(range(2014, 2023))
DISEASES = ["cancer", "total", "diabetes", "cerebrovascular", "heart_disease",
            "kidney", "hypertensive", "liver"]
METHODS = ["scalebb", "loglin_trend", "always_down", "sign_last_change", "majority_direction"]  # [ADD 2026-09-03] majority_direction


def subdir_for(cutoff: int) -> str | None:
    return None if cutoff == 2014 else f"cutoff_{cutoff}"


def main() -> None:
    (OUT / "tables").mkdir(parents=True, exist_ok=True)
    (OUT / "figures").mkdir(parents=True, exist_ok=True)

    long_all = []
    for c in CUTOFFS:
        sub = subdir_for(c)
        if sub is not None and not (BASE / sub / "tables" / "validation_long.csv").exists():
            print(f"[rolling] skip cutoff {c}: output/{sub}/ not found (run run_all.sh)")
            continue
        long_all.append(cda.compute_directional(c, sub))
    long_df = pd.concat(long_all, ignore_index=True)
    summary = cda.summarize(long_df)
    st = summary[(summary["sex"] == "total") & (summary["method"].isin(METHODS))].copy()
    st = st[["cutoff", "method", "disease", "n_cells_evaluable", "dir_acc_pct",
             "majority_pct", "pred_down_pct", "pt_pvalue"]]
    st.to_csv(OUT / "tables" / "rolling_origin_da.csv", index=False)
    print(f"wrote rolling_origin_da.csv ({len(st)} rows)")

    # [ADD 2026-09-03] 予測方向別の的中率 (査読 A-1 (3b)): 「上昇」と答えたセル / 「下落」と答えたセルの的中率と、
    # 予測と実績が独立な場合に期待される DA。sex=total、低下継続 6 系列プールと 8 系列プール。
    six = ["total", "cancer", "diabetes", "cerebrovascular", "heart_disease", "kidney"]
    cond_rows = []
    for label, dis in [("six_declining", six), ("all8", DISEASES)]:
        x = long_df[(long_df["sex"] == "total") & long_df["disease"].isin(dis) & long_df["evaluable"]
                    & long_df["method"].isin(["scalebb", "loglin_trend", "sign_last_change"])]
        for (c, m), g in x.groupby(["cutoff", "method"]):
            up, dn = g[g["pred_sign"] > 0], g[g["pred_sign"] < 0]
            p_up, a_up = (g["pred_sign"] > 0).mean(), (g["actual_sign"] > 0).mean()
            indep = (p_up * a_up + (1 - p_up) * (1 - a_up)) * 100
            cond_rows.append({"series": label, "cutoff": c, "method": m, "n": len(g),
                              "DA": round(g["match"].mean() * 100, 2), "DA_indep": round(indep, 2),
                              "actual_up_pct": round(a_up * 100, 2),
                              "n_pred_up": len(up), "acc_pred_up": round(up["match"].mean() * 100, 2) if len(up) else np.nan,
                              "n_pred_down": len(dn), "acc_pred_down": round(dn["match"].mean() * 100, 2) if len(dn) else np.nan})
    pd.DataFrame(cond_rows).to_csv(OUT / "tables" / "rolling_origin_conditional_da.csv", index=False)
    print("wrote rolling_origin_conditional_da.csv")

    # [ADD 2026-09-03] rolling design の勝敗 (8 疾病 × 9 cutoff = 72 比較)
    sbda = st[st["method"] == "scalebb"].set_index(["cutoff", "disease"])["dir_acc_pct"]
    wl = []
    for m in [mm for mm in METHODS if mm != "scalebb"]:
        o = st[st["method"] == m].set_index(["cutoff", "disease"])["dir_acc_pct"]
        j = pd.concat([sbda.rename("sb"), o.rename("o")], axis=1).dropna()
        wl.append({"vs": m, "n": len(j), "wins": int((j["sb"] > j["o"] + 1e-9).sum()),
                   "ties": int((abs(j["sb"] - j["o"]) <= 1e-9).sum()), "losses": int((j["sb"] < j["o"] - 1e-9).sum())})
    pd.DataFrame(wl).to_csv(OUT / "tables" / "rolling_origin_winloss.csv", index=False)
    print("wrote rolling_origin_winloss.csv")

    # MAPE gap to best baseline per cutoff (sex=total)
    gap_rows = []
    for c in CUTOFFS:
        sub = subdir_for(c)
        d = BASE / sub if sub else BASE
        if not (d / "tables" / "validation_summary.csv").exists():
            continue
        sb = pd.read_csv(d / "tables" / "validation_summary.csv")
        bl = pd.read_csv(d / "tables" / "validation_summary_baseline.csv")
        sb = sb[sb["sex"] == "total"][["disease", "MAPE_pct"]]
        bl = bl[bl["sex"] == "total"].groupby("disease")["MAPE_pct"].min().rename("best_baseline")
        m = sb.merge(bl, on="disease")
        m["gap_pp"] = m["MAPE_pct"] - m["best_baseline"]
        m["cutoff"] = c
        gap_rows.append(m)
    gap = pd.concat(gap_rows, ignore_index=True)
    gap.to_csv(OUT / "tables" / "rolling_origin_mape_gap.csv", index=False)
    print("wrote rolling_origin_mape_gap.csv")

    # ---------- heatmap: DA of Scale BB-D and reference rows ----------
    fig, axes = plt.subplots(1, 3, figsize=(17, 5.2), sharey=True)
    panels = [("scalebb", "Scale BB-D"), ("loglin_trend", "loglin_trend"),
              ("majority_direction", "majority_direction (ex-post benchmark of each window)")]  # [CHG 2026-09-03]
    for ax, (m, title) in zip(axes, panels):
        pv = st[st["method"] == m].pivot(index="disease", columns="cutoff", values="dir_acc_pct")
        pv = pv.reindex(DISEASES)
        im = ax.imshow(pv.values, cmap="RdYlGn", vmin=0, vmax=100, aspect="auto")
        ax.set_xticks(range(len(pv.columns)))
        ax.set_xticklabels(pv.columns)
        ax.set_yticks(range(len(pv.index)))
        ax.set_yticklabels(pv.index)
        ax.set_title(title)
        ax.set_xlabel("training cutoff $y_c$ (validation $y_c$+1 .. 2024)")
        for i in range(pv.shape[0]):
            for j in range(pv.shape[1]):
                v = pv.values[i, j]
                if np.isfinite(v):
                    ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=8,
                            color="black" if 25 < v < 80 else "white")
        # shade the pandemic-adjacent cutoffs
        for j, c in enumerate(pv.columns):
            if c >= 2019:
                ax.axvline(j - 0.5, color="black", lw=0.5, alpha=0.3)
    fig.colorbar(im, ax=axes, fraction=0.015, pad=0.01, label="directional accuracy [%]")
    fig.suptitle("Rolling-origin directional accuracy by training cutoff (sex=total). "
                 "Cutoffs ≥2019: validation window lies inside / after the COVID-19 shock", fontsize=11)
    out = OUT / "figures" / "rolling_origin_da_heatmap.png"
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out.name}")

    # ---------- console summary ----------
    print()
    print("=== rolling-origin DA (sex=total) ===")
    for m in METHODS:
        print(f"--- {m}")
        print(st[st["method"] == m].pivot(index="disease", columns="cutoff", values="dir_acc_pct")
              .reindex(DISEASES).round(1).to_string())
    print("--- majority-direction share")
    print(st[st["method"] == "scalebb"].pivot(index="disease", columns="cutoff", values="majority_pct")
          .reindex(DISEASES).round(1).to_string())
    print("--- Scale BB-D MAPE gap to best baseline [pp]")
    print(gap.pivot(index="disease", columns="cutoff", values="gap_pp").reindex(DISEASES).round(2).to_string())


if __name__ == "__main__":
    main()
