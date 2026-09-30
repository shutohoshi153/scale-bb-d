"""論文本文 (sections/) に掲載する図の生成・収集.

2 つの仕事をする:

  1. 本文 §3・§4 用の説明図を新規生成する
       fig_3_1_input_panel_overview.png      入力パネルの概観 (§3.1)
       fig_3_2_smoothing_before_after.png    平滑化前後の比較 (§3.2.1, 式 3.1–3.2)
       fig_3_3_blend_schematic.png           改善率ブレンドの実例 (§3.2.2, 式 3.5)
       fig_4_1_backtest_design.png           3 cutoff 設計の模式図 (§4.2)
  2. §5 が参照するバックテスト成果図を output/ から収集する
       (output/ は git 管理外のため、本文が参照する図は sections/figures/ に
        コミットする。output/ 側が未生成の場合は警告してスキップ)

出力先はいずれも reproduction/backtest/output/paper_figures/（2026-09-02 変更。旧: Paper_ICA2026/sections/figures/）。
run_all.sh の最終ステップとして実行される (単体実行も可)。
"""
from __future__ import annotations

import shutil
from pathlib import Path

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

# 本文図の置き場 (コミット対象)
# [CHANGE 2026-09-02] 出力先を output/paper_figures/ に変更。旧既定の Paper_ICA2026/sections/figures/ は
# 共著者と共有済みのドラフト版（凍結）であり、再実行で上書きしない。論文（final/sections/figures/）へは
# 明示的にコピーする（final/README.md のビルド手順参照）。旧挙動は環境変数 PAPER_FIG_DIR で指定可。
import os
SECTIONS_FIGS = Path(os.environ["PAPER_FIG_DIR"]) if os.environ.get("PAPER_FIG_DIR") else _paths.OUTPUT_DIR / "paper_figures"
SECTIONS_FIGS.mkdir(parents=True, exist_ok=True)

AGE_MIN, AGE_MAX = 20, 89

# run_backtest.py と同一のハイパーパラメータ (§3.2.3)
SCALE_BB_CONFIG = dict(
    long_term_rate=0.01,
    convergence_year=2035,
    lam_row=40.0,
    lam_col=20.0,  # [FIX 2026-09-02] 暦年グリッド化に伴い 40 → 20 (感度は小: 2014 MAPE 差 0.2pp 以内)
    diff_order=2,
    age_taper_start=90,
    age_taper_end=120,
)


def load_panel() -> pd.DataFrame:
    # build_panel.py 未実行でも動くよう、同梱の照合用パネルへフォールバック
    path = _paths.PANEL if _paths.PANEL.exists() else (
        _paths.DATA_DIR / "prebuilt_disease_panel_mortality.csv"
    )
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
# 図 3.1 — 入力パネルの概観 (§3.1)
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
# 図 3.2 — 平滑化前後の比較 (§3.2.1, 式 3.1–3.2)
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
    # [FIX 2026-09-02] 年軸を暦年の連続グリッドに reindex (欠測年は NaN → 重み 0)。run_backtest.py::build_matrix と同じ修正。
    piv = piv.reindex(columns=range(int(piv.columns.min()), cutoff + 1))
    ages = piv.index.to_numpy(dtype=int)
    years = piv.columns.to_numpy(dtype=int)
    cfg = ScaleBBConfig(last_observed_year=cutoff, **SCALE_BB_CONFIG)
    fit = fit_scale_bb(piv.to_numpy(dtype=float), ages=ages, years=years, config=cfg)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    cmap = plt.get_cmap("tab10")

    # 左: 暦年方向の断面 (代表年齢)
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

    # 右: 年齢方向の断面 (代表暦年)
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
# 図 3.3 — 観測改善率から長期率へのブレンド (§3.2.2, 式 3.5)
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
    # [FIX 2026-09-02] 年軸を暦年の連続グリッドに reindex (欠測年は NaN → 重み 0)。run_backtest.py::build_matrix と同じ修正。
    piv = piv.reindex(columns=range(int(piv.columns.min()), cutoff + 1))
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
# 図 4.1 — 3 cutoff 設計の模式図 (§4.2)
# ---------------------------------------------------------------------------
def make_backtest_design():
    cutoffs = [2014, 2021, 2022]
    T = 2024
    fig, ax = plt.subplots(figsize=(9, 3.2))
    for row, yc in enumerate(cutoffs):
        y = len(cutoffs) - 1 - row  # 上から 2014, 2021, 2022
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
# §5 用 — バックテスト成果図の収集 (output/ → sections/figures/)
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
    # §6.2 / §6.3 (図 6.3 は make_calibration_recovery_figure.py が直接生成)
    "directional/figures/scalebb_directional_per_cutoff.png":
        "fig_6_1_scalebb_directional_per_cutoff.png",
    "directional/figures/scalebb_vs_loglin_directional.png":
        "fig_6_2_scalebb_vs_loglin_directional.png",
    # [ADD 2026-09-02] rolling-origin heatmap (§6.2, compute_rolling_origin.py)
    "directional/figures/rolling_origin_da_heatmap.png":
        "fig_6_4_rolling_origin_da_heatmap.png",
}


def collect_backtest_figures():
    for src_rel, dst_name in COLLECT.items():
        src = _paths.OUTPUT_DIR / src_rel
        if not src.exists():
            print(f"WARN: {src_rel} が未生成のためスキップ (先に run_all.sh を実行)")
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
