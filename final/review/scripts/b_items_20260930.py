"""審査 B-4・B-9・B-10 (2026-09-30): 独立なセルでの勝敗数、0 値・同値セルの除外の感度、ホライズン別 MAPE.

B-4: sex = total は男女の合計、死因 total は各死因を含む。勝敗数を男女 16 セル (8 系列 × 2 性) と
     全死因を除く 14 セル (7 死因 × 2 性) で数え直す。
B-9: DA は実績変化が 0 のセル (同値) を、MAPE は実績率が 0 のセルを除外する。系列別の件数と、
     同値を不正解・0.5 点として数えた場合の DA を示す。
B-10: cutoff 2014 のホライズン別 MAPE (低下継続 6 系列の平均)。

実行: cd reproduction/backtest && ../../../../.venv/bin/python ../../final/review/scripts/b_items_20260930.py
出力: final/review/b_items_stdout_20260930.md (標準出力を保存)
"""
from __future__ import annotations
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, ".")
import _paths  # noqa: E402
import compute_directional_accuracy as cda  # noqa: E402

BASE = _paths.OUTPUT_DIR
D8 = ["total", "heart_disease", "cancer", "cerebrovascular", "kidney", "liver", "diabetes", "hypertensive"]
SIX = ["total", "heart_disease", "cancer", "cerebrovascular", "kidney", "diabetes"]
MAIN = [2014, 2021, 2022]


def tdir(c, level="observed"):
    if level != "observed":
        return BASE / f"base_{level}_cutoff_{c}" / "tables"
    return BASE / "tables" if c == 2014 else BASE / f"cutoff_{c}" / "tables"


def mape(c, level="observed"):
    sb = pd.read_csv(tdir(c, level) / "validation_long.csv").assign(method="scalebb")
    bl = pd.read_csv(tdir(c) / "validation_long_baseline.csv")
    df = pd.concat([sb, bl]); df = df[df["actual_rate_per_100k"] > 0]
    m = df.groupby(["disease", "sex", "method"])["abs_rel_error"].mean().mul(100).unstack("method")
    m["best"] = m[["naive_last", "mean_3pts", "loglin_trend"]].min(axis=1)
    m["worst"] = m[["naive_last", "mean_3pts", "loglin_trend"]].max(axis=1)
    return m


def subsets(idx):
    sex = idx.get_level_values("sex"); dis = idx.get_level_values("disease")
    return {"24 (all)": np.ones(len(idx), bool), "16 (male, female)": sex != "total",
            "14 (male, female; all-cause excluded)": (sex != "total") & (dis != "total")}


def b4():
    print("## B-4 (1) Scale BB-D が最良ベースライン / 少なくとも 1 つのベースラインを MAPE で上回るセル数\n")
    rows = []
    for level in ("observed", "mean_obs"):
        for c in MAIN:
            m = mape(c, level)
            for name, mask in subsets(m.index).items():
                x = m[mask]
                rows.append({"start": level, "cutoff": c, "cells": name, "n": len(x),
                             "beats best": int((x.scalebb < x.best - 1e-9).sum()), "beats at least one": int((x.scalebb < x.worst - 1e-9).sum())})
    print(pd.DataFrame(rows).pivot_table(index=["start", "cells"], columns="cutoff", values=["beats best", "beats at least one"]).to_markdown())

    print("\n## B-4 (2) 同一起点での Scale BB-D 対 対数線形の傾き (表 5.5 最終行)\n")
    c = pd.read_csv(BASE / "cutoff_comparison" / "tables" / "same_anchor_cells.csv")
    w = c.pivot_table(index=["cutoff", "disease", "sex"], columns=["anchor", "trend"], values="MAPE")
    rows = []
    for cut in MAIN:
        x = w.loc[cut]
        for name, mask in subsets(x.index).items():
            for a in ("observed", "mean3"):
                rows.append({"cutoff": cut, "cells": name, "anchor": a, "BB-D ahead": int((x[mask][(a, "scalebb")] < x[mask][(a, "loglin")] - 1e-9).sum())})
    print(pd.DataFrame(rows).pivot_table(index=["cells", "anchor"], columns="cutoff", values="BB-D ahead").to_markdown())

    print("\n## B-4 (3) DA の勝 / 分 / 敗: 系列 × cutoff の比較を性別に数える\n")
    def winloss(cutoffs, subdir_of):
        parts = []
        for cut in cutoffs:
            s = cda.summarize(cda.compute_directional(cut, subdir_of(cut)))
            parts.append(s.assign(cutoff=cut))
        s = pd.concat(parts)
        piv = s.pivot_table(index=["cutoff", "disease", "sex"], columns="method", values="dir_acc_pct")
        out = []
        for name, mask in subsets(piv.index).items():
            x = piv[mask]
            if name.startswith("24"):
                x = piv[piv.index.get_level_values("sex") == "total"]; name = "sex = total (8 series)"
            for m in ("loglin_trend", "majority_direction", "always_down", "sign_last_change", "mean_3pts"):
                d = x["scalebb"] - x[m]
                out.append({"cells": name, "vs": m, "n": len(d), "W/T/L": f"{int((d > 1e-9).sum())} / {int((d.abs() <= 1e-9).sum())} / {int((d < -1e-9).sum())}"})
        return pd.DataFrame(out).pivot(index="vs", columns="cells", values="W/T/L")
    print("3 cutoff (2014, 2021, 2022):\n"); print(winloss(MAIN, lambda c: None if c == 2014 else f"cutoff_{c}").to_markdown())
    print("\nrolling (2014–2022):\n"); print(winloss(range(2014, 2023), lambda c: None if c == 2014 else f"cutoff_{c}").to_markdown())


def b9():
    print("\n## B-9 除外セルの件数と同値の扱いの感度 (sex = total)\n")
    panel = pd.read_csv(_paths.PANEL)
    rows = []
    for cut in MAIN:
        long_df = cda.compute_directional(cut, None if cut == 2014 else f"cutoff_{cut}")
        sb = long_df[(long_df["method"] == "scalebb") & (long_df["sex"] == "total")]
        n_years = 2024 - cut
        for d in D8:
            g = sb[sb["disease"] == d]
            ties = int((~g["evaluable"]).sum()); ev = g[g["evaluable"]]
            hit = int(ev["match"].sum()); n_ev = len(ev)
            act = panel[(panel["disease_id"] == d) & (panel["sex"] == "total") & (panel["age_low"].between(20, 85)) & (panel["year"] > cut)]
            zero_actual = int((act["rate_per_100k"] == 0).sum())
            rows.append({"cutoff": cut, "series": d, "grid cells": 14 * n_years, "in DA": n_ev, "ties (actual = cutoff level)": ties,
                         "not in table (no cutoff level / missing)": 14 * n_years - n_ev - ties, "actual rate = 0 (out of MAPE)": zero_actual,
                         "DA": hit / n_ev * 100, "DA ties wrong": hit / (n_ev + ties) * 100, "DA ties 0.5": (hit + 0.5 * ties) / (n_ev + ties) * 100})
    t = pd.DataFrame(rows)
    print(t[t["cutoff"] == 2014].drop(columns="cutoff").round(1).to_markdown(index=False))
    print("\ncutoff 2021 / 2022:\n"); print(t[t["cutoff"] != 2014].round(1).to_markdown(index=False))
    x = t[t.cutoff == 2014]
    print("\ncutoff 2014: 最大の DA の変化 (同値を不正解 / 0.5 点):", round((x["DA"] - x["DA ties wrong"]).max(), 1), "/", round((x["DA"] - x["DA ties 0.5"]).abs().max(), 1))


def b10():
    print("\n## B-10 cutoff 2014 のホライズン別 MAPE [%] (sex = total、低下継続 6 系列の平均)\n")
    sb = pd.read_csv(tdir(2014) / "validation_long.csv").assign(method="scalebb")
    bl = pd.read_csv(tdir(2014) / "validation_long_baseline.csv")
    df = pd.concat([sb, bl]); df = df[(df["actual_rate_per_100k"] > 0) & (df["sex"] == "total") & df["disease"].isin(SIX)]
    df["h"] = df["year"] - 2014
    m = df.groupby(["h", "disease", "method"])["abs_rel_error"].mean().mul(100).groupby(["h", "method"]).mean().unstack("method")
    m["rank of scalebb (1 = best)"] = m[["scalebb", "naive_last", "mean_3pts", "loglin_trend"]].rank(axis=1)["scalebb"]
    print(m.round(1).to_markdown())
    by = df[df["h"] == 10].groupby(["disease", "method"])["abs_rel_error"].mean().mul(100).unstack("method")
    print("\n10 年先で Scale BB-D が最良の系列:", [d for d in by.index if by.loc[d, "scalebb"] <= by.loc[d].min() + 1e-9])


if __name__ == "__main__":
    b4(); b9(); b10()
