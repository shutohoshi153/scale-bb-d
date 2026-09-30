#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BEL 感応度の一表・図生成(BEL感応度デモ・Python層②)。

【位置づけ】
    作業指示書 §6 の aggregate_fms_results.py に相当。フォールバック運用のため、
    入力は FMS 出力ではなく calc_bel_standalone.py(簡易 Python 版・主計算)の
    出力 bel_by_mp_scenario.csv とする。

【入力】ScaleBB/Research/output/bel_demo/bel_by_mp_scenario.csv
【出力】(ScaleBB/Research/output/bel_demo/)
    - bel_sensitivity_table.csv  行: MP01–MP08 + 合計(9 行)
        列: BASE_PV, UP50_PV, UP50_pct, DN50_PV, DN50_pct,
            ICS_T_PV, ICS_T_pct, ICS_C_PV, ICS_C_pct(pct は BASE 比変化率 %)
    - bel_sensitivity_bar.png    加入年齢順のモデルポイント別・シナリオ別
        BASE 比変化率 % の棒グラフ(論文 §8 の図)
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# --- パス(再現パッケージ・自己完結。定義は _paths.py) ----------------------
from _paths import OUTPUT_DIR as OUT_DIR  # noqa: E402

# シナリオの固定順序と色(検証済みカテゴリカルパレット。順序は循環させない)
SCN_ORDER = ["UP50", "DN50", "ICS_T", "ICS_C", "ESR_M"]
SCN_COLOR = {"UP50": "#1f77b4", "DN50": "#ff7f0e",
             "ICS_T": "#d62728", "ICS_C": "#9467bd", "ESR_M": "#2ca02c"}
SCN_LABEL = {"UP50": "UP50 (L=1.5%)", "DN50": "DN50 (L=0.5%)",
             "ICS_T": "ICS_T (L=0%)", "ICS_C": "ICS_C (L=0%, ×1.125)",
             "ESR_M": "ESR_M (BASE ×1.125)"}


def build_table(bel: pd.DataFrame) -> pd.DataFrame:
    """MP 別 + 合計の感応度一表(PV と BASE 比 %)を組む。"""
    wide = bel.pivot_table(index="MP_ID", columns="SCN_CD", values="BEL")
    wide.loc["合計"] = wide.sum()
    tbl = pd.DataFrame(index=wide.index)
    tbl["BASE_PV"] = wide["BASE"]
    for scn in SCN_ORDER:
        tbl[f"{scn}_PV"] = wide[scn]
        tbl[f"{scn}_pct"] = 100.0 * (wide[scn] / wide["BASE"] - 1.0)
    return tbl


def plot_bars(bel: pd.DataFrame, path: Path) -> None:
    """加入年齢順のモデルポイント別・シナリオ別 BASE 比変化率の棒グラフ。"""
    wide = bel.pivot_table(index="MP_ID", columns="SCN_CD", values="BEL")
    meta = bel.drop_duplicates("MP_ID").set_index("MP_ID")
    # 加入年齢順(同年齢は男→女)に並べ、年齢効果が読み取れるようにする
    mp_order = meta.sort_values(["ISSUE_AGE", "GNDR_CD"],
                                ascending=[True, False]).index.tolist()
    pct = 100.0 * (wide.loc[mp_order, SCN_ORDER].div(wide.loc[mp_order, "BASE"], axis=0) - 1.0)
    labels = [f"{meta.at[mp, 'ISSUE_AGE']}{meta.at[mp, 'GNDR_CD']}" for mp in mp_order]

    x = np.arange(len(mp_order))
    n = len(SCN_ORDER)
    width = 0.155  # 群内に僅かな地の隙間を残す細めのバー(5 本/群)
    fig, ax = plt.subplots(figsize=(10, 4.6))
    for k, scn in enumerate(SCN_ORDER):
        pos = x + (k - (n - 1) / 2) * (width + 0.015)
        vals = pct[scn].to_numpy()
        ax.bar(pos, vals, width=width, color=SCN_COLOR[scn], label=SCN_LABEL[scn])
        for xi, v in zip(pos, vals):  # 直接値ラベル(色に依存しない読み取りの担保)
            ax.annotate(f"{v:+.1f}", (xi, v), ha="center",
                        va="bottom" if v >= 0 else "top",
                        fontsize=7, color="#333333",
                        xytext=(0, 1.5 if v >= 0 else -1.5),
                        textcoords="offset points")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_xticks(x, labels)
    ax.set_xlabel("Model point (issue age / sex)")
    ax.set_ylabel("Change in BEL vs BASE (%)")
    ax.grid(axis="y", alpha=0.25, linewidth=0.6)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.margins(y=0.15)
    ax.legend(frameon=False, ncol=5, loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main() -> None:
    bel = pd.read_csv(OUT_DIR / "bel_by_mp_scenario.csv")
    tbl = build_table(bel)
    tbl.to_csv(OUT_DIR / "bel_sensitivity_table.csv",
               index_label="MP_ID", float_format="%.6g")
    plot_bars(bel, OUT_DIR / "bel_sensitivity_bar.png")
    with pd.option_context("display.float_format", "{:,.1f}".format):
        print(tbl.to_string())
    print(f"\n出力: {OUT_DIR / 'bel_sensitivity_table.csv'}")
    print(f"出力: {OUT_DIR / 'bel_sensitivity_bar.png'}")


if __name__ == "__main__":
    main()
