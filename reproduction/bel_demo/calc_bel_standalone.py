#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BEL(給付現価)簡易計算 — フォールバック主計算(BEL感応度デモ)。

【位置づけ】
    作業指示書 §7 の verify_bel_standalone.py(V1b・FMS クロスチェック用)を、
    §8 のフォールバック規定(7/24 判断点)に基づき主計算へ昇格させたもの。
    FMS Booster 実行環境(DB_ASSUMP)が未接続のため、FMS 実行は「今後の検証」とし、
    本スクリプトの独立実装 BEL を論文 §8 の一表の計算主体とする。

【計算式】年次ステップ、決定論的。[CHG 2026-09-30] 死因別死亡給付としての評価に改めた:
    BEL(x0) = Σ_t  P(t) · S(t) · q_dis(x0+t, 2026+t) · SA
    S(0) = 1,  S(t+1) = S(t) · (1 − q_dis − q_other − q_lapse)
    [CHG 2026-09-30] q は中央死亡率 m から q_tot = 1 − exp(−m_dis − m_other)、q_dis = q_tot·m_dis/(m_dis + m_other)
    で求める (to_probabilities)。率表 scn_claim_rates.csv / scn_mortality_rates.csv は中央死亡率 m (10 万で除した値) のまま
    q_dis   = 3 死因(がん・心疾患・脳血管疾患)のシナリオ別死亡率の合計(給付事由 = 3 死因による死亡)
    q_other = その他の死因の死亡率 = 全死因 BASE − 3 死因 BASE(全シナリオ共通 — トレンド感応度を
              3 死因の率のみに帰着)。水準ストレスを含むシナリオ(ICS_C・ESR_M)では ×1.125
    q_lapse = 0.03 固定、SA = 100 万円
    P(t)    = ESR 無リスク金利カーブ(JPY・2026年3月末基準)の割引係数。
              金融庁イールド・カーブ作成ツールのパラメータ(LOT=30年、UFR=3.8%、
              収束年限=60年)から Smith-Wilson 補外で再現(build_esr_discount_curve.py)

    2026-09-03 版までは健康事象の発現で支払う給付として S(t+1) = S(t)·(1 − q_dis − q_death − q_lapse)
    (q_death = 全死因)としていた。死亡給付として読むと 3 死因による死亡が q_dis と q_death の両方で
    脱退に入り二重計上になる(審査指摘 B-11)。旧式の結果は reference_output_20260903/ に残し、
    final/review/scripts/death_benefit_reading_a6.py が新旧を並べて再現する。

【経済価値ベース(ESR)仕様への準拠と簡略化】
    - BEL は「現在推計」(基準日で再評価した将来キャッシュフローの現価)に対応する。
      MOCE(不確実性マージン)・所要資本の統合計算は本デモの範囲外
    - 感応度は 1柱告示のストレス方式(ストレス適用後の再計算による純資産減少額)と
      同型: 資産側を不変とすれば ΔBEL がそのまま純資産変動に対応する
    - ESR_M シナリオは告示第56条の死亡リスク(日本: 死亡率 +12.5%)のストレスを全死因
      (3 死因とその他の死因)に適用したもの
    - 割引は無リスク金利カーブのみ(一般バケット等のスプレッド調整は未適用)
    - 脱退の同時発生調整(FMS C03 の 0.5 クロス項)は行わない。
      給付は年次・期始割引(P(t))で評価。デモの目的は「方向と桁」の提示

【入力】data/processed/bel_demo/scn_claim_rates.csv, scn_mortality_rates.csv,
        esr_jpy_spot_curve_20260331.csv
【出力】(ScaleBB/Research/output/bel_demo/)
    - bel_by_mp_scenario.csv   MP_ID × SCN_CD 別の BEL(円)
    - verify_bel_checks.csv    V2(単調性)・V3(合成整合)の機械チェック結果
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pandas as pd

# --- パス(再現パッケージ・自己完結。定義は _paths.py) ----------------------
from _paths import PROCESSED_DIR as DATA_DIR, OUTPUT_DIR as OUT_DIR  # noqa: E402

# --- 前提(作業指示書 §3 + ESR 仕様) --------------------------------------
SUM_ASSURED = 1_000_000        # 三大疾病一時金 100 万円
LAPSE_RATE = 0.03              # 解約率 年 3% 固定(全シナリオ共通)
SCENARIOS = ["BASE", "UP50", "DN50", "ICS_T", "ICS_C", "ESR_M"]
ICS_LEVEL_FACTOR = 1.125
ESR_MORTALITY_FACTOR = 1.125   # 告示第56条 死亡リスク(日本: 死亡率 +12.5%)
# 水準ストレスを含むシナリオ: その他の死因の死亡率にも同じ係数をかける
LEVEL_STRESSED = {"ICS_C": ICS_LEVEL_FACTOR, "ESR_M": ESR_MORTALITY_FACTOR}

# モデルポイント定義(MP01–04 男 / MP05–08 女、加入年齢 30/40/50/60)
MODEL_POINTS = [
    {"MP_ID": f"MP{i + 1:02d}", "GNDR_CD": g, "ISSUE_AGE": a}
    for i, (g, a) in enumerate(
        [(g, a) for g in ("M", "F") for a in (30, 40, 50, 60)])
]


def load_discount_factors(n: int) -> np.ndarray:
    """ESR 無リスク金利カーブから割引係数 P(t)(t=0..n−1)を読み込む。"""
    curve = pd.read_csv(DATA_DIR / "esr_jpy_spot_curve_20260331.csv")
    p = curve.set_index("MATURITY")["DISCOUNT_FACTOR"]
    assert p.index.max() >= n - 1, "割引カーブの年限が不足"
    return np.array([1.0] + [p[t] for t in range(1, n)])


def other_cause_rates(q_dis_base: np.ndarray, q_death_base: np.ndarray) -> np.ndarray:
    """その他の死因の死亡率 = 全死因 BASE − 3 死因 BASE(負にならないことを確認)。"""
    other = q_death_base - q_dis_base
    assert (other > -1e-12).all(), "3 死因の率が全死因を上回るセルがある"
    return np.maximum(other, 0.0)


def to_probabilities(m_dis: np.ndarray, m_other: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """[ADD 2026-09-30] 中央死亡率 m (年率、人口あたり) を 1 年死亡確率 q に変換する (再審査 A-9)。

    各年齢・年で死亡の力が一定と仮定し (一定ハザード近似)、全死因の確率 q = 1 − exp(−m_dis − m_other) を
    死因別の率に比例して配分する (競合リスク): q_dis = q · m_dis / (m_dis + m_other)、q_other = q − q_dis。
    2026-09-30 の再審査対応までは q ≈ m (率をそのまま確率として控除) としていた。
    """
    m_dis = np.asarray(m_dis, dtype=float); m_other = np.asarray(m_other, dtype=float)
    m_tot = m_dis + m_other
    q_tot = -np.expm1(-m_tot)
    with np.errstate(invalid="ignore", divide="ignore"):
        q_dis = np.where(m_tot > 0, q_tot * m_dis / m_tot, 0.0)
    return q_dis, q_tot - q_dis


def bel_single(m_dis: np.ndarray, m_other: np.ndarray, disc: np.ndarray,
               lapse: float = LAPSE_RATE) -> float:
    """1 モデルポイント・1 シナリオの BEL(給付現価)を計算する。

    m_dis は給付事由 (3 死因による死亡) の中央死亡率、m_other はその他の死因の中央死亡率 (脱退のみ)。
    to_probabilities で 1 年死亡確率に変換してから用いる。

    lapse は解約率(既定は共通仮定 3%)。calc_esr_life_risk.py の
    解約・失効リスクストレスで ±25% を適用する際に差し替える。
    """
    q_dis, q_other = to_probabilities(m_dis, m_other)
    surv = 1.0
    bel = 0.0
    for t in range(len(q_dis)):
        bel += disc[t] * surv * q_dis[t] * SUM_ASSURED
        surv *= max(0.0, 1.0 - q_dis[t] - q_other[t] - lapse)
    return bel


def main() -> None:
    t0 = time.perf_counter()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    claims = pd.read_csv(DATA_DIR / "scn_claim_rates.csv")
    morts = pd.read_csv(DATA_DIR / "scn_mortality_rates.csv")

    # q_dis: 3 給付項目の合計をデュレーション順に並べる
    q_dis_tbl = (claims.groupby(["SCN_CD", "GNDR_CD", "ISSUE_AGE", "DUR"])["ASSM_RT"]
                 .sum().sort_index())
    q_death_tbl = (morts.set_index(["GNDR_CD", "ISSUE_AGE", "DUR"])["ASSM_RT"]
                   .sort_index())

    disc_full = load_discount_factors(60)  # 最長デュレーション(x0=30 → 60 年)

    rows = []
    for mp in MODEL_POINTS:
        g, a = mp["GNDR_CD"], mp["ISSUE_AGE"]
        q_death = q_death_tbl.loc[(g, a)].to_numpy()
        q_other = other_cause_rates(q_dis_tbl.loc[("BASE", g, a)].to_numpy(), q_death)
        disc = disc_full[: 90 - a]
        for scn in SCENARIOS:
            q_dis = q_dis_tbl.loc[(scn, g, a)].to_numpy()
            assert len(q_dis) == len(q_death) == 90 - a
            rows.append({**mp, "SCN_CD": scn,
                         "BEL": bel_single(q_dis, q_other * LEVEL_STRESSED.get(scn, 1.0), disc)})
    result = pd.DataFrame(rows)
    result.to_csv(OUT_DIR / "bel_by_mp_scenario.csv", index=False)

    # --- V2: 単調性(L 上昇 → 罹患率低下 → 給付 PV 減少)、V3: 合成整合 ------
    wide = result.pivot_table(index="MP_ID", columns="SCN_CD", values="BEL")
    checks = []
    order = ["UP50", "BASE", "DN50", "ICS_T", "ICS_C"]
    for lo, hi in zip(order[:-1], order[1:]):
        ok = bool((wide[lo] < wide[hi]).all())
        checks.append({"check": f"V2 単調性 {lo} < {hi}", "passed": ok})
    # ICS_C ≒ ICS_T × 1.125 からの乖離は生存(脱退)相互作用分のみ(小・負方向)。
    # 実測 1.10–1.11 程度(若年 MP ほど期間が長く相互作用が大きい)。
    # 帯 (1.05, 1.125] は符号・桁の取り違え検出用で、相互作用分は許容する
    ratio = wide["ICS_C"] / wide["ICS_T"]
    checks.append({
        "check": "V3 合成整合 ICS_C / ICS_T vs 1.125",
        "passed": bool(((ratio > 1.05) & (ratio <= ICS_LEVEL_FACTOR + 1e-9)).all()),
        "detail": f"min={ratio.min():.4f}, max={ratio.max():.4f}",
    })
    # ESR_M(死亡率+12.5%のレベルショック)は BASE を上回り、比は 1.125 以下(脱退相互作用)
    ratio_esr = wide["ESR_M"] / wide["BASE"]
    checks.append({
        "check": "V3 合成整合 ESR_M / BASE vs 1.125",
        "passed": bool(((ratio_esr > 1.05) & (ratio_esr <= ESR_MORTALITY_FACTOR + 1e-9)).all()),
        "detail": f"min={ratio_esr.min():.4f}, max={ratio_esr.max():.4f}",
    })
    checks_df = pd.DataFrame(checks)
    checks_df.to_csv(OUT_DIR / "verify_bel_checks.csv", index=False)

    elapsed = time.perf_counter() - t0
    print(result.pivot_table(index="MP_ID", columns="SCN_CD", values="BEL")
          .loc[:, order + ["ESR_M"]].round(0).to_string())
    all_ok = checks_df["passed"].all()
    print(f"\nV2/V3 チェック: {'全合格' if all_ok else '不合格あり'} 所要 {elapsed:.2f} 秒")
    assert all_ok, "V2/V3 チェック不合格(verify_bel_checks.csv 参照)"


if __name__ == "__main__":
    main()
