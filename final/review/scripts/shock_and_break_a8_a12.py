"""再審査 A-8・A-12 (2026-09-30): ショック期の学習効果の識別、hypertensive の分類改訂の補正.

A-8  ショック期の年を学習に含めた効果を、予測期間・予測対象年・収束期間から切り離して測る。
     (1) 固定ホライズン (h = 1, 2, 3) の比較を、収束年 2035 固定ではなく収束期間 N = 12 年 (P = y_c + 12) で
         全起点に揃えてやり直す。
     (2) 同じ起点・同じ起点水準 (観測率)・同じ予測対象年・同じ N について、学習データに 2020–2022 年を
         含む fit (A) と、それらの年を重み 0 にした fit (B) を比べる (cutoff 2020–2023)。差は学習データの
         違いだけから生じる。
A-12 hypertensive の 2017 年の段差 (死因分類の改訂) を補正した系列で同じバックテストを行う。
     補正係数は年齢・性ごとに 2016→2017 年の対数変化から前後 1 年の平均変化を差し引いたもの
     (段差のうちトレンドで説明されない部分)。死亡数の少ない年齢 (2016・2017 年の率が 0.5 未満) は
     性別の全年齢合計の死亡数から同じ方法で求めた係数を用いる。2017 年以降の値を係数で割り、旧分類の
     基準にそろえる。あわせて、主要な集計を hypertensive を除いて数え直す。

実行: cd reproduction/backtest && OPENBLAS_NUM_THREADS=1 ../../../../.venv/bin/python ../../final/review/scripts/shock_and_break_a8_a12.py
出力: final/review/a8_a12_*_20260930.csv、標準出力 (final/review/a8_a12_stdout_20260930.md に保存する)
"""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, ".")
import _paths  # noqa: E402
import run_backtest as rb  # noqa: E402
from experience_rate._scalebb_core.model import ScaleBBConfig, fit_scale_bb, project_scale_bb  # noqa: E402

REVIEW_DIR = Path(__file__).resolve().parents[1]
DISEASES = ["total", "heart_disease", "cancer", "cerebrovascular", "kidney", "liver", "diabetes", "hypertensive"]
SEXES = ["total", "male", "female"]
SHOCK = (2020, 2021, 2022)
N_CONV = 12
LAST = 2024
CFG = {k: v for k, v in rb.SCALE_BB_CONFIG.items() if k != "convergence_year"}


def actual(df, dis, sex, ages, years):
    return (df[(df.disease_id == dis) & (df.sex == sex) & df.year.isin(years)]
            .pivot_table(index="age_low", columns="year", values="rate_per_100k").reindex(index=ages, columns=years).to_numpy(float))


def run(df, dis, sex, c, drop_shock=False):
    ages, years, rates = rb.build_matrix(df, disease=dis, sex=sex, year_max=c)
    w = np.where(np.isfinite(rates) & (rates > 0), 1.0, 0.0)
    if drop_shock:
        for y in SHOCK:
            if y < c and y in years:  # 起点年そのものは起点水準として残す
                w[:, list(years).index(y)] = 0.0
    cfg = ScaleBBConfig(last_observed_year=c, horizon_year=LAST, convergence_period=N_CONV, **CFG)
    f = project_scale_bb(fit_scale_bb(rates, ages=ages, years=years, config=cfg, weight=w), base_year=c)
    vy = list(range(c + 1, LAST + 1))
    P = np.stack([f.rate_projected[:, int(np.where(f.projection_years == y)[0][0])] for y in vy], axis=1)
    base = rates[:, list(years).index(c)]
    return ages, vy, P, actual(df, dis, sex, ages, vy), base


def metrics(P, A, base):
    v = np.isfinite(A) & (A > 0) & np.isfinite(P)
    mape = float(np.mean(np.abs(P[v] - A[v]) / A[v]) * 100)
    b = base[:, None]
    ev = np.isfinite(A) & (b > 0) & (A != b) & np.isfinite(P)
    da = float(np.mean(np.sign(P[ev] - np.broadcast_to(b, P.shape)[ev]) == np.sign(A[ev] - np.broadcast_to(b, A.shape)[ev])) * 100) if ev.any() else np.nan
    return mape, da


def a8(df):
    print("## A-8 (1) 固定ホライズン、収束期間 N = 12 年を全起点で共通 (sex = total、8 系列平均 MAPE [%])\n")
    rows = []
    for c in range(2014, 2024):
        for dis in DISEASES:
            ages, vy, P, A, base = run(df, dis, "total", c)
            for h in (1, 2, 3):
                if c + h > LAST:
                    continue
                k = vy.index(c + h)
                rows.append({"cutoff": c, "h": h, "disease": dis, "MAPE": metrics(P[:, [k]], A[:, [k]], base)[0]})
    fh = pd.DataFrame(rows)
    fh.to_csv(REVIEW_DIR / "a8_a12_fixed_horizon_N12_20260930.csv", index=False)
    print(fh.groupby(["cutoff", "h"]).MAPE.mean().unstack("h").round(1).to_markdown())

    print("\n## A-8 (2) 同じ起点・対象年・N で、学習に 2020–2022 年を含む (A) か含まない (B) か\n")
    rows = []
    for c in (2020, 2021, 2022, 2023):
        for dis in DISEASES:
            for sex in SEXES:
                res = {}
                for lab, drop in (("A_with_shock", False), ("B_without_shock", True)):
                    _, vy, P, A, base = run(df, dis, sex, c, drop_shock=drop)
                    res[lab] = metrics(P, A, base)
                rows.append({"cutoff": c, "disease": dis, "sex": sex,
                             "MAPE_A": res["A_with_shock"][0], "MAPE_B": res["B_without_shock"][0],
                             "DA_A": res["A_with_shock"][1], "DA_B": res["B_without_shock"][1]})
    cf = pd.DataFrame(rows)
    cf.to_csv(REVIEW_DIR / "a8_a12_shock_in_training_20260930.csv", index=False)
    t = cf[cf.sex == "total"]
    s = t.groupby("cutoff")[["MAPE_A", "MAPE_B", "DA_A", "DA_B"]].mean()
    s["MAPE_A−B"] = s.MAPE_A - s.MAPE_B; s["DA_A−B"] = s.DA_A - s.DA_B
    print("8 系列平均 (sex = total):\n"); print(s.round(1).to_markdown())
    ind = cf[(cf.sex != "total") & (cf.disease != "total")]
    cnt = ind.groupby("cutoff").apply(lambda g: pd.Series({
        "A better MAPE (of 14)": int((g.MAPE_A < g.MAPE_B - 1e-9).sum()),
        "B better MAPE": int((g.MAPE_B < g.MAPE_A - 1e-9).sum()),
        "A better DA": int((g.DA_A > g.DA_B + 1e-9).sum()), "B better DA": int((g.DA_B > g.DA_A + 1e-9).sum())}), include_groups=False)
    print("\n独立な 14 セル (7 死因 × 男女):\n"); print(cnt.to_markdown())
    print("\n系列別 MAPE の A − B (sex = total):\n")
    print(t.assign(d=t.MAPE_A - t.MAPE_B).pivot(index="disease", columns="cutoff", values="d").loc[DISEASES].round(1).to_markdown())


def bridged_panel(df):
    h = df[df.disease_id == "hypertensive"].copy()
    fac = {}
    for sex in SEXES:
        s = h[h.sex == sex]
        dth = s[s.age_low.between(20, 85)].groupby("year").deaths.sum()
        pooled = np.log(dth[2017] / dth[2016]) - 0.5 * (np.log(dth[2016] / dth[2015]) + np.log(dth[2018] / dth[2017]))
        for a in sorted(s.age_low.unique()):
            r = s[s.age_low == a].set_index("year").rate_per_100k
            if all(y in r.index for y in (2015, 2016, 2017, 2018)) and min(r[2016], r[2017]) >= 0.5 and min(r[2015], r[2018]) > 0:
                step = np.log(r[2017] / r[2016]) - 0.5 * (np.log(r[2016] / r[2015]) + np.log(r[2018] / r[2017]))
            else:
                step = pooled
            fac[(sex, a)] = step
    h["step"] = [fac[(s, a)] for s, a in zip(h.sex, h.age_low)]
    post = h.year >= 2017
    h.loc[post, "rate_per_100k"] = h.loc[post, "rate_per_100k"] / np.exp(h.loc[post, "step"])
    h.loc[post, "deaths"] = h.loc[post, "deaths"] / np.exp(h.loc[post, "step"])
    steps = h.drop_duplicates(["sex", "age_low"]).pivot(index="age_low", columns="sex", values="step")
    return h.drop(columns="step"), steps


def a12(df):
    print("\n## A-12 (1) 補正係数 exp(step) (2017 年以降の値をこれで割る)\n")
    h, steps = bridged_panel(df)
    print(np.exp(steps.loc[20:85]).round(2).to_markdown())
    path = REVIEW_DIR / "a8_a12_hypertensive_bridged_panel_20260930.csv"
    h.to_csv(path, index=False)
    print("\n補正後の sex = total、年齢 60–85 の率 (2013–2024):\n")
    x = h[(h.sex == "total") & h.age_low.between(60, 85) & (h.year >= 2013)].pivot(index="age_low", columns="year", values="rate_per_100k")
    print(x.round(1).to_markdown())

    env = dict(os.environ, SCALEBB_PANEL=str(path))
    import compute_directional_accuracy as cda
    rows = []
    for c in range(2014, 2023):
        sub = f"a12_bridged_cutoff_{c}"
        common = ["--train-cutoff", str(c), "--validation-end", str(LAST), "--output-subdir", sub]
        for cmd in (["run_backtest.py", *common], ["run_baselines.py", *common, "--trend-window", "15"]):
            subprocess.run([sys.executable, *cmd], env=env, check=True, capture_output=True)
        d = cda.summarize(cda.compute_directional(c, sub))
        d = d[d.sex == "total"].set_index("method")
        v = pd.read_csv(_paths.OUTPUT_DIR / sub / "tables" / "validation_summary.csv").query("sex == 'total'").iloc[0]
        vb = pd.read_csv(_paths.OUTPUT_DIR / sub / "tables" / "validation_summary_baseline.csv").query("sex == 'total'")
        rows.append({"cutoff": c, "DA_scalebb": d.loc["scalebb", "dir_acc_pct"], "DA_loglin": d.loc["loglin_trend", "dir_acc_pct"],
                     "majority": d.loc["scalebb", "majority_pct"], "pred_down": d.loc["scalebb", "pred_down_pct"],
                     "MAPE_scalebb": v.MAPE_pct, "MAPE_best_baseline": vb.MAPE_pct.min(), "bias_scalebb": v.mean_rel_bias_pct})
    res = pd.DataFrame(rows)
    res.to_csv(REVIEW_DIR / "a8_a12_hypertensive_bridged_backtest_20260930.csv", index=False)
    orig = pd.read_csv(_paths.OUTPUT_DIR / "directional" / "tables" / "rolling_origin_da.csv")
    o = orig[(orig.disease == "hypertensive")].pivot_table(index="cutoff", columns="method", values="dir_acc_pct")
    res["DA_scalebb_unbridged"] = res.cutoff.map(o["scalebb"])
    print("\n## A-12 (2) 補正系列でのバックテスト (hypertensive, sex = total)\n")
    print(res.round(1).to_markdown(index=False))


def a12_counts():
    print("\n## A-12 (3) hypertensive を除いた集計\n")
    BT = _paths.OUTPUT_DIR / "directional" / "tables"
    s = pd.read_csv(BT / "directional_summary.csv")
    p = s.pivot_table(index=["cutoff", "disease", "sex"], columns="method", values="dir_acc_pct")
    rows = []
    for name, mask in (("sex = total, 8 series", (p.index.get_level_values("sex") == "total")),
                       ("sex = total, 7 series (no hypertensive)", (p.index.get_level_values("sex") == "total") & (p.index.get_level_values("disease") != "hypertensive")),
                       ("men and women, 7 causes", (p.index.get_level_values("sex") != "total") & (p.index.get_level_values("disease") != "total")),
                       ("men and women, 6 causes (no hypertensive)", (p.index.get_level_values("sex") != "total") & ~p.index.get_level_values("disease").isin(["total", "hypertensive"]))):
        x = p[mask]
        for m in ("loglin_trend", "majority_direction", "mean_3pts", "always_down", "sign_last_change"):
            d = x["scalebb"] - x[m]
            rows.append({"cells": name, "vs": m, "W/T/L": f"{int((d > 1e-9).sum())} / {int((d.abs() <= 1e-9).sum())} / {int((d < -1e-9).sum())}"})
    print("DA の勝 / 分 / 敗 (3 cutoff):\n"); print(pd.DataFrame(rows).pivot(index="vs", columns="cells", values="W/T/L").to_markdown())
    rows = []
    for c in (2014, 2021, 2022):
        d = _paths.OUTPUT_DIR / ("tables" if c == 2014 else f"cutoff_{c}/tables")
        sb = pd.read_csv(d / "validation_long.csv").assign(method="scalebb"); bl = pd.read_csv(d / "validation_long_baseline.csv")
        z = pd.concat([sb, bl]); z = z[z.actual_rate_per_100k > 0]
        m = z.groupby(["disease", "sex", "method"]).abs_rel_error.mean().unstack("method")
        best = m[["naive_last", "mean_3pts", "loglin_trend"]].min(axis=1)
        ind = (m.index.get_level_values("sex") != "total") & (m.index.get_level_values("disease") != "total")
        noh = ind & (m.index.get_level_values("disease") != "hypertensive")
        rows.append({"cutoff": c, "beats best, 14 cells": int((m.scalebb[ind] < best[ind]).sum()),
                     "beats best, 12 cells (no hypertensive)": int((m.scalebb[noh] < best[noh]).sum())})
    print("\nMAPE で最良ベースラインを上回るセル数:\n"); print(pd.DataFrame(rows).to_markdown(index=False))


if __name__ == "__main__":
    panel = pd.read_csv(_paths.PANEL)
    a8(panel)
    a12(panel)
    a12_counts()
