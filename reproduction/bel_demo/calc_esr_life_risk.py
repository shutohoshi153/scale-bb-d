#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ESR 生命保険リスク所要資本・MOCE・保険負債の簡易計算(BEL感応度デモ拡張)。

【目的】
    1柱告示(令和7年金融庁告示第74号)の標準的手法に従い、デモポートフォリオ
    (8 モデルポイント、3 死因による死亡を給付事由とする死亡給付として評価。[CHG 2026-09-30])について以下を計算する。

    1. 生命保険リスクのサブリスク 5 種(ストレス方式、日本の地理的区分):
       - 死亡リスク    (第56条: 死亡率 +12.5%。3 死因とその他の死因の両方に適用。ESR_M の ΔBEL に一致)
       - 長寿リスク    (第57条: 死亡率 −20%。死亡給付では現価が減るため 0)
       - 罹患・障害リスク(第59・60条: 本商品は死亡給付のため対象外 → 0)
       - 解約・失効リスク(第61〜63条: 水準トレンド ±25% と大量解約 30% の大きい方)
       - 経費リスク    (第64条: 本デモは経費キャッシュフローなし → 0)
    2. 生命保険リスクの統合(第81条の相関行列による平方根統合)
    3. MOCE(第29・30条: 資本コスト率 3%、推計所要資本(t) はランオフ・パターン
       近似 — 第30条第3項。パターンは割引後給付キャッシュフローの残存割合で近似)
    4. 保険負債 = 現在推計(BASE の BEL)+ MOCE

【範囲外(明示)】
    市場・信用・オペリスク、リスクカテゴリー間の統合、適格資本、ESR 比率そのもの
    (資産側を持たないため)。損害保険・巨大災害リスクも対象外。
    2026-09-03 版までは健康事象の発現で支払う給付(罹患・障害リスク +20%)として計算していた。
    その結果は reference_output_20260903/esr_life_risk_summary.csv に残る。

【入力】data/processed/bel_demo/ の率 CSV・割引カーブ(calc_bel_standalone と共通)
【出力】output/bel_demo/esr_life_risk_summary.csv(MP 別サブリスク+合計・統合・MOCE)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from calc_bel_standalone import (
    DATA_DIR,
    LAPSE_RATE,
    MODEL_POINTS,
    OUT_DIR,
    SUM_ASSURED,
    bel_single,
    load_discount_factors,
    other_cause_rates,
)

# --- 告示のストレス係数(日本の地理的区分) --------------------------------
MORT_STRESS = 1.125       # 第56条 死亡リスク: 死亡率 +12.5%
LONGEVITY_STRESS = 0.80   # 第57条 長寿リスク: 死亡率 −20%
LAPSE_UP, LAPSE_DOWN = 1.25, 0.75   # 第62条 解約・失効(水準トレンド): ±25%
MASS_LAPSE = 0.30         # 第63条 大量解約: 30%(団体年金以外)
COST_OF_CAPITAL = 0.03    # 第29条 MOCE: 資本コスト率 3%

# 第81条 生命保険リスクの相関行列(死亡・長寿・罹患障害・解約失効・経費の順)
CORR = np.array([
    [1.00, -0.25, 0.25, 0.00, 0.25],
    [-0.25, 1.00, 0.00, 0.25, 0.25],
    [0.25, 0.00, 1.00, 0.00, 0.50],
    [0.00, 0.25, 0.00, 1.00, 0.50],
    [0.25, 0.25, 0.50, 0.50, 1.00],
])
SUBRISK_NAMES = ["死亡", "長寿", "罹患・障害", "解約・失効", "経費"]


def main() -> None:
    claims = pd.read_csv(DATA_DIR / "scn_claim_rates.csv")
    morts = pd.read_csv(DATA_DIR / "scn_mortality_rates.csv")
    q_dis_tbl = (claims[claims["SCN_CD"] == "BASE"]
                 .groupby(["GNDR_CD", "ISSUE_AGE", "DUR"])["ASSM_RT"].sum().sort_index())
    q_death_tbl = (morts.set_index(["GNDR_CD", "ISSUE_AGE", "DUR"])["ASSM_RT"].sort_index())
    disc_full = load_discount_factors(60)

    rows = []
    pattern_num = None  # MOCE ランオフ・パターン用: 年度別の割引後給付 CF(全 MP 合算)
    for mp in MODEL_POINTS:
        g, a = mp["GNDR_CD"], mp["ISSUE_AGE"]
        q_dis = q_dis_tbl.loc[(g, a)].to_numpy()
        q_death = q_death_tbl.loc[(g, a)].to_numpy()
        disc = disc_full[: 90 - a]
        q_other = other_cause_rates(q_dis, q_death)
        base = bel_single(q_dis, q_other, disc)

        # サブリスク: ストレス後 BEL − BASE(純資産減少額。負なら 0 — 告示の各条但書)
        # 死亡・長寿のストレスは全死因(給付事由の 3 死因とその他の死因)に一律にかける
        d_mort = bel_single(q_dis * MORT_STRESS, q_other * MORT_STRESS, disc) - base
        d_long = bel_single(q_dis * LONGEVITY_STRESS, q_other * LONGEVITY_STRESS, disc) - base
        d_morb = 0.0  # 罹患・障害リスク: 死亡給付のため対象外
        d_lapse_ud = max(
            bel_single(q_dis, q_other, disc, lapse=LAPSE_RATE * LAPSE_UP) - base,
            bel_single(q_dis, q_other, disc, lapse=LAPSE_RATE * LAPSE_DOWN) - base,
        )
        d_mass = (1.0 - MASS_LAPSE) * base - base  # 基準日に 30% が解約(解約返戻金なし)
        rows.append({
            **mp, "BASE_BEL": base,
            "死亡": max(0.0, d_mort), "長寿": max(0.0, d_long),
            "罹患・障害": max(0.0, d_morb),
            "解約・失効(水準トレンド)": max(0.0, d_lapse_ud),
            "解約・失効(大量解約)": max(0.0, d_mass),
            "経費": 0.0,
        })

        # MOCE パターン素材: 割引後給付 CF の年度別配列(残存割合の近似に使う)
        surv = np.concatenate([[1.0], np.cumprod(
            np.maximum(0.0, 1.0 - q_dis - q_other - LAPSE_RATE))[:-1]])
        cf = disc * surv * q_dis * SUM_ASSURED
        cf_pad = np.zeros(60)
        cf_pad[: len(cf)] = cf
        pattern_num = cf_pad if pattern_num is None else pattern_num + cf_pad

    df = pd.DataFrame(rows)

    # ポートフォリオ合計のサブリスクと統合(第61条: 解約は水準トレンドと大量解約の大きい方)
    total = {name: df[name].sum() for name in ["死亡", "長寿", "罹患・障害", "経費"]}
    total["解約・失効"] = max(df["解約・失効(水準トレンド)"].sum(),
                          df["解約・失効(大量解約)"].sum())
    v = np.array([total[n] for n in SUBRISK_NAMES])
    life_risk = float(np.sqrt(v @ CORR @ v))
    undiversified = float(v.sum())

    # MOCE(第29・30条): 推計所要資本(t) = 統合リスク × ランオフ・パターン(t)。
    # パターンは割引後給付 CF の残存割合(第30条第3項の「適切な指標」による近似)
    remaining = pattern_num[::-1].cumsum()[::-1]
    pattern = remaining / remaining[0]
    moce = COST_OF_CAPITAL * float((life_risk * pattern * disc_full).sum())
    base_total = df["BASE_BEL"].sum()
    liability = base_total + moce

    df.to_csv(OUT_DIR / "esr_life_risk_by_mp.csv", index=False, float_format="%.2f")
    summary = pd.DataFrame([
        {"項目": f"サブリスク: {n}", "額(円)": total[n]} for n in SUBRISK_NAMES
    ] + [
        {"項目": "生命保険リスク(相関統合後・第81条)", "額(円)": life_risk},
        {"項目": "(参考)単純合算", "額(円)": undiversified},
        {"項目": "(参考)分散効果", "額(円)": life_risk - undiversified},
        {"項目": "現在推計(BASE BEL 合計)", "額(円)": base_total},
        {"項目": "MOCE(資本コスト率3%・第29条)", "額(円)": moce},
        {"項目": "保険負債(現在推計+MOCE)", "額(円)": liability},
    ])
    summary.to_csv(OUT_DIR / "esr_life_risk_summary.csv", index=False, float_format="%.2f")

    with pd.option_context("display.float_format", "{:,.0f}".format):
        print(summary.to_string(index=False))
    print(f"\n検算: 死亡 {total['死亡']:,.0f} 円 は ESR_M シナリオの ΔBEL と一致するはず")
    print(f"MOCE / 現在推計 = {moce / base_total:.2%}")


if __name__ == "__main__":
    main()
