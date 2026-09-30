"""審査 A-7 (2026-09-30): 長期率 L の感応度幅 (0.5〜1.5%) の根拠 — 過去の 10 年平均改善率の分布.

§8 の 3 死因 (がん・心疾患・脳血管疾患) × 男女について、観測率から 10 年間の年平均改善率
    1 − (m(x, y+10) / m(x, y))^(1/10)
を年齢 20–85 歳 (14 階級) × 10 年区間 (1950→60, …, 2000→10, 2014→24 の 7 区間) で計算し、その分布を要約する。
L は「収束後に持続すると仮定する改善率」なので、過去の 10 年平均がどの範囲にあったかが幅の目安になる。

実行: cd reproduction/backtest && ../../../../.venv/bin/python ../../final/review/scripts/l_range_a7.py
出力: final/review/l_range_a7_20260930.csv、標準出力に Markdown 表
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, ".")
import _paths  # noqa: E402

REVIEW_DIR = Path(__file__).resolve().parents[1]
DIS = ["cancer", "heart_disease", "cerebrovascular"]
PERIODS = [(1950, 1960), (1960, 1970), (1970, 1980), (1980, 1990), (1990, 2000), (2000, 2010), (2014, 2024)]


def main() -> None:
    df = pd.read_csv(_paths.PANEL)
    df = df[df["disease_id"].isin(DIS) & df["sex"].isin(["male", "female"]) & (df["age_low"] >= 20) & (df["age_low"] <= 85)]
    piv = df.pivot_table(index=["disease_id", "sex", "age_low"], columns="year", values="rate_per_100k")
    rows = []
    for a, b in PERIODS:
        with np.errstate(divide="ignore", invalid="ignore"):
            imp = (1.0 - (piv[b] / piv[a]) ** (1.0 / (b - a))) * 100
        for (dis, sex, age), v in imp.items():
            if np.isfinite(v):
                rows.append({"disease": dis, "sex": sex, "age_low": age, "period": f"{a}-{b}", "improvement_pct": v})
    out = pd.DataFrame(rows)
    out.to_csv(REVIEW_DIR / "l_range_a7_20260930.csv", index=False)

    def summ(g):
        v = g["improvement_pct"]
        return pd.Series({"n": len(v), "p10": v.quantile(0.10), "p25": v.quantile(0.25), "median": v.median(),
                          "p75": v.quantile(0.75), "p90": v.quantile(0.90),
                          "share_below_0": (v < 0).mean() * 100, "share_0.5_to_1.5": ((v >= 0.5) & (v <= 1.5)).mean() * 100,
                          "share_above_1.5": (v > 1.5).mean() * 100})
    print("## 10 年平均改善率 [%/年] の分布: 系列別 (年齢 20–85 × 7 区間)\n")
    print(out.groupby(["disease", "sex"]).apply(summ, include_groups=False).round(2).to_markdown())
    print("\n## 区間別 (3 死因 × 男女 × 年齢をプール)\n")
    print(out.groupby("period").apply(summ, include_groups=False).round(2).to_markdown())
    print("\n## 全体\n")
    print(summ(out).round(2).to_frame("all").T.to_markdown())
    old = out[out["age_low"] >= 60]
    print("\n## 60 歳以上のみ\n")
    print(summ(old).round(2).to_frame("age 60+").T.to_markdown())


if __name__ == "__main__":
    main()
