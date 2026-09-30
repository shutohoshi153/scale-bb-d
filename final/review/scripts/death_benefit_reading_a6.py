"""審査 A-6 / B-11 (2026-09-30): §8 のデモの新旧 2 つの計算を並べる.

新 (現行の式 8.1・表 8.3): 3 死因による死亡を給付事由とする死亡給付。
    S(t+1) = S(t) · (1 − q_dis − q_other − q_lapse),  q_other = 全死因 BASE − 3 死因 BASE
    水準ストレス ESR_M = 死亡率 +12.5% (告示第 56 条) を 3 死因とその他の死因に適用。
旧 (2026-09-03 版までの式 8.1。実稼働モデルで突合したのはこちら、§9.2): 健康事象の発現で支払う給付。
    S(t+1) = S(t) · (1 − q_dis − q_death − q_lapse),  q_death = 全死因 (3 死因を含むため二重に脱退する)
    水準ストレス = 発生率 +20% (告示第 59・60 条)。

入力: reproduction/bel_demo/data/processed/ (bel_demo/run_all.sh の生成物)
実行: cd reproduction/bel_demo && ../../../../.venv/bin/python ../../final/review/scripts/death_benefit_reading_a6.py
出力: final/review/death_benefit_reading_20260930.csv、標準出力に Markdown 表
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

REVIEW_DIR = Path(__file__).resolve().parents[1]
D = Path("data/processed")
SA, LAPSE = 1_000_000.0, 0.03
TREND = ["BASE", "UP50", "DN50", "ICS_T"]


def bel(q_claim, q_decrement, disc):
    s, b = 1.0, 0.0
    for t in range(len(q_claim)):
        b += disc[t] * s * q_claim[t] * SA
        s *= max(0.0, 1.0 - q_decrement[t] - LAPSE)
    return b


def main() -> None:
    claims = pd.read_csv(D / "scn_claim_rates.csv")
    morts = pd.read_csv(D / "scn_mortality_rates.csv")
    curve = pd.read_csv(D / "esr_jpy_spot_curve_20260331.csv").set_index("MATURITY")["DISCOUNT_FACTOR"]
    disc = np.array([1.0] + [curve[t] for t in range(1, 60)])
    q = claims.groupby(["SCN_CD", "GNDR_CD", "ISSUE_AGE", "DUR"])["ASSM_RT"].sum().sort_index()
    qd = morts.set_index(["GNDR_CD", "ISSUE_AGE", "DUR"])["ASSM_RT"].sort_index()
    rows = []
    for g in ("M", "F"):
        for a in (30, 40, 50, 60):
            base, dth = q.loc[("BASE", g, a)].to_numpy(), qd.loc[(g, a)].to_numpy()
            other = np.maximum(dth - base, 0.0)
            r = {"MP": f"{a} {g}", "share_3causes_min": float((base / dth).min()), "share_3causes_max": float((base / dth).max())}
            for scn in TREND:
                x = q.loc[(scn, g, a)].to_numpy()
                r[f"old_{scn}"] = bel(x, x + dth, disc)
                r[f"new_{scn}"] = bel(x, other + x, disc)
            r["old_LEVEL"] = bel(base * 1.20, base * 1.20 + dth, disc)                 # 発生率 +20%
            r["new_LEVEL"] = bel(base * 1.125, (other + base) * 1.125, disc)            # 死亡率 +12.5% (= ESR_M)
            rows.append(r)
    t = pd.DataFrame(rows)
    tot = {"MP": "Total", **{c: t[c].sum() for c in t.columns if c.startswith(("old_", "new_"))}}
    t = pd.concat([t, pd.DataFrame([tot])], ignore_index=True)
    t.to_csv(REVIEW_DIR / "death_benefit_reading_20260930.csv", index=False)
    for k, title in (("new", "新: 死亡給付 (現行の表 8.3。LEVEL = 死亡率 +12.5%)"), ("old", "旧: 健康事象で支払う給付 (2026-09-03 版の表 8.3。LEVEL = 発生率 +20%)")):
        o = pd.DataFrame({"MP": t["MP"], "BASE BEL": t[f"{k}_BASE"].round(0)})
        for s in TREND[1:] + ["LEVEL"]:
            o[s] = ((t[f"{k}_{s}"] / t[f"{k}_BASE"] - 1) * 100).round(1)
        print(f"\n## {title}: BASE 比 [%]\n"); print(o.to_markdown(index=False))
    d = pd.DataFrame({"MP": t["MP"], "BASE BEL new/old − 1 [%]": ((t["new_BASE"] / t["old_BASE"] - 1) * 100).round(1)})
    for s in TREND[1:]:
        d[f"{s} 差 [pp]"] = ((t[f"new_{s}"] / t["new_BASE"] - t[f"old_{s}"] / t["old_BASE"]) * 100).round(2)
    print("\n## 新旧の差\n"); print(d.to_markdown(index=False))
    print("\n全死因に占める 3 死因の割合 (BASE、到達年齢別の最小–最大):",
          f"{t['share_3causes_min'].min():.2f}–{t['share_3causes_max'].max():.2f}")


if __name__ == "__main__":
    main()
