"""審査 A-8 (2026-09-30): 死亡数重み付き平滑化の感度分析 — バックテスト・末端の安定性.

式 (3.1) は全セルを等重みで扱う。ここでは重みを死亡数 (対数率の分散 ≈ 1/死亡数、Poisson) に替えた
フィット (fit_scale_bb(..., weight=deaths)。重みは観測セル平均 1 に正規化、λ は不変) を等重みと比べる。

(1) バックテスト: cutoff 2014 / 2021 / 2022、8 系列 × 3 性、MAPE と DA (run_backtest と同じ設定・観測率起点)
(2) 末端水準オフセット: 平滑化率と観測率の差 |log(m~/m)| の年齢帯別平均 (cutoff 2014–2023、低下継続 6 系列 × 3 性)
(3) 末端改善率の改訂: 学習窓を 1 年延ばしたときの i(x, y_c) の変化と符号反転率 (boundary_bias.py と同じ定義)

BEL 感応度 (表 8.3) の重み付き版は reproduction/bel_demo を BEL_DEMO_VARIANT=deathweight で実行する。

実行:  cd reproduction/backtest && OPENBLAS_NUM_THREADS=1 ../../../../.venv/bin/python ../../final/review/scripts/weighted_smoothing_a8.py
出力:  final/review/weighted_a8_backtest_cells_20260930.csv / weighted_a8_boundary_20260930.csv、標準出力に Markdown 表
"""
from __future__ import annotations
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
SIX = ["total", "cancer", "diabetes", "cerebrovascular", "heart_disease", "kidney"]
SEXES = ["total", "male", "female"]
BANDS = [(20, 34, "20-34"), (35, 59, "35-59"), (60, 89, "60-89")]
LAST_YEAR = 2024


def matrices(df, dis, sex, ymax):
    ages, years, rates = rb.build_matrix(df, disease=dis, sex=sex, year_max=ymax)
    sub = df[(df["disease_id"] == dis) & (df["sex"] == sex)]
    deaths = (sub.pivot_table(index="age_low", columns="year", values="deaths", aggfunc="mean")
              .reindex(index=ages, columns=years).to_numpy(dtype=float))
    return ages, years, rates, deaths


def fit(df, dis, sex, ymax, weighted):
    ages, years, rates, deaths = matrices(df, dis, sex, ymax)
    cfg = ScaleBBConfig(last_observed_year=ymax, horizon_year=LAST_YEAR, **rb.SCALE_BB_CONFIG)
    f = fit_scale_bb(rates, ages=ages, years=years, config=cfg, weight=deaths if weighted else None)
    return ages, years, rates, f


def backtest(df):
    rows = []
    for c in (2014, 2021, 2022):
        vy = list(range(c + 1, LAST_YEAR + 1))
        for dis in DISEASES:
            for sex in SEXES:
                act = (df[(df["disease_id"] == dis) & (df["sex"] == sex) & df["year"].isin(vy)]
                       .pivot_table(index="age_low", columns="year", values="rate_per_100k"))
                for weighted in (False, True):
                    ages, years, rates, f = fit(df, dis, sex, c, weighted)
                    f = project_scale_bb(f, base_year=c)
                    A = act.reindex(index=ages, columns=vy).to_numpy(dtype=float)
                    P = np.stack([f.rate_projected[:, int(np.where(f.projection_years == y)[0][0])] for y in vy], axis=1)
                    obs_c = rates[:, int(np.where(years == c)[0][0])]
                    v = np.isfinite(A) & (A > 0) & np.isfinite(P)
                    d_act, d_pred = A - obs_c[:, None], P - obs_c[:, None]
                    ev = np.isfinite(d_act) & (d_act != 0) & np.isfinite(d_pred)
                    rows.append({"cutoff": c, "disease": dis, "sex": sex, "weight": "deaths" if weighted else "equal",
                                 "MAPE": float(np.mean(np.abs(P[v] - A[v]) / A[v]) * 100),
                                 "DA": float(np.mean(np.sign(d_pred[ev]) == np.sign(d_act[ev])) * 100)})
    out = pd.DataFrame(rows)
    out.to_csv(REVIEW_DIR / "weighted_a8_backtest_cells_20260930.csv", index=False)
    t = out[out["sex"] == "total"]
    print("## (1) バックテスト (sex = total): MAPE [%] / DA [%]、等重み vs 死亡数重み\n")
    w = t.pivot_table(index="disease", columns=["cutoff", "weight"], values="MAPE").loc[DISEASES]
    w.loc["mean (8)"] = w.mean()
    print(w.round(2).to_markdown())
    d = t.pivot_table(index="disease", columns=["cutoff", "weight"], values="DA").loc[DISEASES]
    d.loc["mean (8)"] = d.mean(); d.loc["mean (six declining)"] = d.loc[SIX].mean()
    print(); print(d.round(1).to_markdown())
    p = out.pivot_table(index=["cutoff", "disease", "sex"], columns="weight", values="MAPE")
    print("\n24 セル中、死亡数重みの MAPE が等重みより低いセル数:",
          p.groupby(level="cutoff").apply(lambda g: int((g["deaths"] < g["equal"] - 1e-9).sum())).to_dict())


def boundary(df):
    rows = []
    for dis in SIX:
        for sex in SEXES:
            for weighted in (False, True):
                cache = {y: fit(df, dis, sex, y, weighted) for y in range(2014, LAST_YEAR + 1)}
                for c in range(2014, 2024):
                    ages, years, rates, f0 = cache[c]
                    j0 = int(np.where(years == c)[0][0])
                    i0 = f0.improvement_smoothed[:, j0]
                    _, y1, _, f1 = cache[c + 1]
                    i1 = f1.improvement_smoothed[:, int(np.where(y1 == c)[0][0])]
                    with np.errstate(divide="ignore", invalid="ignore"):
                        off = np.abs(np.log(f0.rate_smoothed[:, j0] / rates[:, j0]))
                    for k, a in enumerate(ages):
                        rows.append({"disease": dis, "sex": sex, "weight": "deaths" if weighted else "equal", "cutoff": c,
                                     "age": int(a), "abs_log_offset": off[k] if np.isfinite(off[k]) else np.nan,
                                     "abs_i": abs(i0[k]) * 100, "rev1_abs_pp": abs(i1[k] - i0[k]) * 100,
                                     "sign_flip": float(np.sign(i1[k]) != np.sign(i0[k]))})
    out = pd.DataFrame(rows)
    out["band"] = pd.cut(out["age"], [19, 34, 59, 89], labels=[b[2] for b in BANDS])
    out.to_csv(REVIEW_DIR / "weighted_a8_boundary_20260930.csv", index=False)
    s = out.groupby(["weight", "band"], observed=True).agg(
        offset_pct=("abs_log_offset", lambda x: x.mean() * 100), mean_abs_i_pp=("abs_i", "mean"),
        rev1_pp=("rev1_abs_pp", "mean"), sign_flip_pct=("sign_flip", lambda x: x.mean() * 100))
    a = out.groupby("weight").agg(offset_pct=("abs_log_offset", lambda x: x.mean() * 100), mean_abs_i_pp=("abs_i", "mean"),
                                  rev1_pp=("rev1_abs_pp", "mean"), sign_flip_pct=("sign_flip", lambda x: x.mean() * 100))
    print("\n## (2)(3) 末端の水準オフセット [%]・|i| [pp]・1 年延長時の改訂幅 [pp]・符号反転率 [%] (低下継続 6 系列 × 3 性、cutoff 2014–2023)\n")
    print(s.round(2).to_markdown()); print(); print(a.round(2).to_markdown())


if __name__ == "__main__":
    panel = pd.read_csv(_paths.PANEL)
    backtest(panel)
    boundary(panel)
