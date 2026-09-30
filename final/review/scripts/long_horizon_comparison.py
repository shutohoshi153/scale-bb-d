"""60 年地平での挙動比較 (2026-09-04、論文 §7 の新設節と §8 の接続のための計算).

問い: 10 年以内の点精度で同等な手法 (対数線形外挿) は、保険負債の評価地平 (発行 2026 年、90 歳満了 = 最長 60 年)
      でどう振る舞うか。Scale BB-D (L への収束) と比較し、率の経路と BEL の推定窓に対する安定性を測る。

方法:
  - 学習終端 2024、3 疾病 × 男女 (§8 デモと同じ)。年齢 20–89 (5 歳階級)。
  - 対数線形外挿: 直近 W 年 (W = 10, 15, 20) の OLS 勾配 s_x を 2086 年まで延長 (run_baselines.predict_loglin と同形)。
  - Scale BB-D: 論文既定 (L = 1%, P = 2035, 起点 = 観測率)。参考に L = 0.5% / 1.5%。
  - 指標: (a) 2050 年・2086 年の率の比 (対 2024 年観測)、(b) §8 と同じ BEL (8 モデルポイント、ESR 割引カーブ、解約 3%、
    死亡脱退は Scale BB-D BASE 全死因で共通) を各テーブルで計算し、W に対する感度 (BEL の変動幅) を測る。
出力: final/review/long_horizon_paths_20260904.csv, long_horizon_bel_20260904.csv,
      final/sections/figures/fig_7_1_long_horizon_paths.png, 標準出力に Markdown 表
実行:  cd reproduction/backtest && ../../../../.venv/bin/python ../../final/review/scripts/long_horizon_comparison.py
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, ".")
import _paths  # noqa: E402
import run_backtest as rb  # noqa: E402
from experience_rate._scalebb_core.model import ScaleBBConfig, fit_scale_bb, project_scale_bb  # noqa: E402

HERE = Path(__file__).resolve()
REVIEW_DIR = HERE.parents[1]
FIG_DIR = HERE.parents[1].parent / "sections" / "figures"
BEL_DIR = HERE.parents[3] / "reproduction" / "bel_demo"
DIS = ["cancer", "heart_disease", "cerebrovascular"]
SEXES = ["male", "female"]
LAST, ISSUE, MAT, HORIZON = 2024, 2026, 90, 2086
WINDOWS = [10, 15, 20]
AGE_LOWS = list(range(20, 90, 5))
SUM_ASSURED, LAPSE = 1_000_000, 0.03
COMMON = dict(convergence_year=2035, lam_row=40.0, lam_col=20.0, diff_order=2, age_taper_start=90, age_taper_end=120)


def loglin_surface(rates, years, W):
    yrs = years.astype(float); mask = years >= LAST - W + 1
    out_years = np.arange(LAST, HORIZON + 1)
    S = np.full((rates.shape[0], out_years.size), np.nan)
    for i in range(rates.shape[0]):
        r = rates[i, mask]; x = yrs[mask]; ok = np.isfinite(r) & (r > 0)
        if ok.sum() < 3:
            continue
        b, a = np.polyfit(x[ok], np.log(r[ok]), 1)
        # 起点は 2024 年観測率 (Scale BB-D と同じ) にそろえ、勾配のみ外挿する
        S[i, :] = rates[i, -1] * np.exp(b * (out_years - LAST))
    return out_years, S


def scalebb_surface(rates, ages, years, L):
    cfg = ScaleBBConfig(long_term_rate=L, last_observed_year=LAST, horizon_year=HORIZON, **COMMON)
    f = project_scale_bb(fit_scale_bb(rates, ages=ages, years=years, config=cfg), base_year=LAST)
    return f.projection_years, f.rate_projected


def diagonal(S, years, x0):
    yi = {int(y): k for k, y in enumerate(years)}
    return np.array([S[AGE_LOWS.index(min(85, ((x0 + d) // 5) * 5)), yi[ISSUE + d]] / 1e5 for d in range(MAT - x0)])


def bel(q_dis, q_other, disc):
    # [CHG 2026-09-30] §8 と同じ死亡給付の計算: 3 死因 (q_dis) とその他の死因 (q_other) を 1 回ずつ脱退させる
    surv, v = 1.0, 0.0
    for t in range(len(q_dis)):
        v += disc[t] * surv * q_dis[t] * SUM_ASSURED
        surv *= max(0.0, 1.0 - q_dis[t] - q_other[t] - LAPSE)
    return v


def main():
    df = pd.read_csv(_paths.PANEL)
    curve = pd.read_csv(BEL_DIR / "data" / "processed" / "esr_jpy_spot_curve_20260331.csv").set_index("MATURITY")["DISCOUNT_FACTOR"]
    disc_full = np.array([1.0] + [curve[t] for t in range(1, 60)])
    surfaces = {}   # (dis, sex, method) -> (years, S)
    path_rows = []
    for sex in SEXES:
        for dis in DIS + ["total"]:
            ages, years, rates = rb.build_matrix(df, disease=dis, sex=sex, year_max=LAST)
            j = int(np.where(years == LAST)[0][0]); base = rates[:, j]
            for L in (0.01, 0.005, 0.015):
                y, S = scalebb_surface(rates, ages, years, L); surfaces[(dis, sex, f"scalebb_L{L*100:.1f}")] = (y, S)
            for W in WINDOWS:
                y, S = loglin_surface(rates, years, W); surfaces[(dis, sex, f"loglin_W{W}")] = (y, S)
            if dis == "total":
                continue
            for (d_, s_, m), (y, S) in surfaces.items():
                if d_ != dis or s_ != sex:
                    continue
                for yy in (2035, 2050, 2086):
                    k = int(np.where(y == yy)[0][0])
                    for i, a in enumerate(ages):
                        path_rows.append({"disease": dis, "sex": sex, "method": m, "year": yy, "age_low": int(a),
                                          "rate": S[i, k], "ratio_to_2024": S[i, k] / base[i] if base[i] > 0 else np.nan})
    paths = pd.DataFrame(path_rows); paths.to_csv(REVIEW_DIR / "long_horizon_paths_20260930.csv", index=False)

    print("## (a) 率の比 (対 2024 年観測)、年齢 40–44 / 70–74、心疾患・男性")
    p = paths[(paths.disease == "heart_disease") & (paths.sex == "male") & paths.age_low.isin([40, 70])]
    print(p.pivot_table(index=["age_low", "method"], columns="year", values="ratio_to_2024").round(3).to_markdown())
    print("\n## (a2) 2086 年の率の比、3 疾病 × 男女、年齢 20–85 の幾何平均")
    g = paths[paths.year == 2086].copy(); g["log"] = np.log(g.ratio_to_2024)
    print(np.exp(g.pivot_table(index=["disease", "sex"], columns="method", values="log", aggfunc="mean")).round(3).to_markdown())

    # BEL
    bel_rows = []
    methods = [m for m in sorted({k[2] for k in surfaces})]
    for sex in SEXES:
        ym, Sm = surfaces[("total", sex, "scalebb_L1.0")]
        for x0 in (30, 40, 50, 60):
            q_death = diagonal(Sm, ym, x0); disc = disc_full[: MAT - x0]
            q_dis_of = lambda m: sum(diagonal(surfaces[(d, sex, m)][1], surfaces[(d, sex, m)][0], x0) for d in DIS)
            # その他の死因 = 全死因 BASE − 3 死因 BASE (Scale BB-D L = 1%)。全手法で共通
            q_other = np.maximum(q_death - q_dis_of("scalebb_L1.0"), 0.0)
            for m in methods:
                bel_rows.append({"sex": sex, "issue_age": x0, "method": m, "BEL": bel(q_dis_of(m), q_other, disc)})
    b = pd.DataFrame(bel_rows); b.to_csv(REVIEW_DIR / "long_horizon_bel_20260930.csv", index=False)
    w = b.pivot_table(index=["sex", "issue_age"], columns="method", values="BEL")
    tot = w.sum().to_frame().T; tot.index = pd.MultiIndex.from_tuples([("total", "—")])
    w = pd.concat([w, tot])
    base_col = "scalebb_L1.0"
    print("\n## (b) BEL (円/100 万円) — 手法・推定窓別")
    print(w.round(0).to_markdown())
    print("\n## (b2) BEL の対 Scale BB-D BASE 比 [%]")
    print(((w.div(w[base_col], axis=0) - 1) * 100).round(1).to_markdown())
    ll = [c for c in w.columns if c.startswith("loglin")]
    sb = [c for c in w.columns if c.startswith("scalebb")]
    rng_ll = (w[ll].max(axis=1) / w[ll].min(axis=1) - 1) * 100
    rng_sb = (w[sb].max(axis=1) / w[sb].min(axis=1) - 1) * 100
    print("\n## (b3) 推定窓 W=10/15/20 での BEL の幅 [%] (対数線形) と L=0.5/1.0/1.5% での幅 [%] (Scale BB-D)")
    print(pd.DataFrame({"loglin_window_range_pct": rng_ll, "scalebb_L_range_pct": rng_sb}).round(1).to_markdown())

    # figure: heart disease male, ages 40 and 70, paths 2013..2086
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    ages, years, rates = rb.build_matrix(df, disease="heart_disease", sex="male", year_max=LAST)
    for ax, a in zip(axes, (40, 70)):
        i = AGE_LOWS.index(a)
        obs_ok = np.isfinite(rates[i]) & (years >= 2000)
        ax.plot(years[obs_ok], rates[i, obs_ok], "k.", label="observed")
        for m, c, ls in [("scalebb_L1.0", "tab:green", "-"), ("scalebb_L0.5", "tab:green", ":"), ("scalebb_L1.5", "tab:green", "--"),
                         ("loglin_W10", "tab:red", ":"), ("loglin_W15", "tab:red", "-"), ("loglin_W20", "tab:red", "--")]:
            y, S = surfaces[("heart_disease", "male", m)]
            ax.plot(y, S[i], color=c, ls=ls, label=m.replace("scalebb_", "Scale BB-D ").replace("loglin_", "log-linear "))
        ax.set_yscale("log"); ax.set_title(f"heart_disease, male, ages {a}–{a+4}"); ax.set_xlabel("year"); ax.set_ylabel("rate per 100,000 (log)")
        ax.axvspan(2020, 2022, color="grey", alpha=0.15); ax.grid(alpha=0.3)
    axes[0].legend(fontsize=7, loc="lower left")
    fig.suptitle("Projected rates to 2086: Scale BB-D (convergence to L) versus log-linear extrapolation (window W)", fontsize=10)
    fig.tight_layout(); FIG_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)  # [ADD 2026-09-30] 公開リポジトリには final/sections/figures が無い
    fig.savefig(FIG_DIR / "fig_7_1_long_horizon_paths.png", dpi=120); print("\nwrote fig_7_1_long_horizon_paths.png")


if __name__ == "__main__":
    main()
