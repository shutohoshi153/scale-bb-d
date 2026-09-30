#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""シナリオ別クレーム率生成(BEL感応度デモ・Python層①)。

【目的】
    ScaleBB の fit を疾病×性別ごとに 1 回だけ実行し(Phase 1 は L に依存しない)、
    long_term_rate (L) のみ差し替えた Phase 2 再投影で 5 シナリオの率サーフェスを
    生成する。モデルポイント別の世代対角線 rate[dur] = m(x0+dur, 2026+dur) を
    デュレーション別率に展開し、per-100k → 小数へ換算して出力する。
    作業指示書 `docs/BEL_Demo_WorkInstruction_FMS_20260710.md` §2(シナリオ定義)・
    §4.1 に準拠。

【運用注記(フォールバック)】
    2026-07-24 のフォールバック判断(作業指示書 §8)により FMS 実行は「今後の検証」
    へ回したため、DB_ASSUMP へのロードは行わず CSV 出力のみとする。
    BEL 計算は calc_bel_standalone.py(簡易 Python 版・主計算)が担う。

【入力】
    - ../../BackTest_2015_2024/data/disease_panel_mortality.csv(死因別死亡率パネル、per 100k)
    - 経験率集計処理ベンダリングコア(ValidationTools/EAS/src/experience_rate/_scalebb_core/model.py)
      の fit_scale_bb / project_scale_bb / ScaleBBConfig

【出力】(ScaleBB/Research/data/processed/bel_demo/)
    - scn_claim_rates.csv       列: SCN_CD, BNFT_Q, GNDR_CD, ISSUE_AGE, DUR, ASSM_RT
    - scn_mortality_rates.csv   全死因・BASE 固定(SCN_CD='BASE', BNFT_Q=0)、同形式
    - rate_surface_{disease}_{sex}_{scn}.csv  検算用サーフェス(per 100k、年齢帯×年)

【受入基準(作業指示書 §4.1。本スクリプト内で機械チェック)】
    - 全 (SCN, BNFT_Q, GNDR, ISSUE_AGE, DUR) の組に欠損なし、率は (0, 1) の範囲内
    - L が大きいシナリオほど将来率が低い(UP50 < BASE < DN50 < ICS_T < ICS_C)
"""
from __future__ import annotations

import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

# --- パス(再現パッケージ・自己完結。定義は _paths.py) ----------------------
from _paths import PANEL_CSV, PROCESSED_DIR as OUT_DIR, VARIANT  # noqa: E402  (vendor/ を sys.path に載せる)
from experience_rate._scalebb_core.model import (  # noqa: E402
    ScaleBBConfig,
    fit_scale_bb,
    project_scale_bb,
)

# --- 仕様定数(作業指示書 §2・§3) -----------------------------------------
ISSUE_YEAR = 2026            # 発行年
MATURITY_AGE = 90            # 90 歳満了(付保は 89 歳まで)
ISSUE_AGES = [30, 40, 50, 60]
LAST_OBSERVED = 2024
HORIZON_YEAR = 2086          # 発行 2026 + 満了 60 年

# シナリオ定義(SCN_CD → long_term_rate)。ICS_C は ICS_T ×1.125 で導出。
# [CHG 2026-09-30] ESR_M は BASE ×1.125 — 死因別死亡給付としての評価に改めたため、1柱告示
# (令和7年金融庁告示第74号)第56条の死亡リスク(日本: 死亡率 12.5%増加)のレベルショックとする。
# 2026-09-03 版までは第59・60条の罹患・障害リスク(発生率 20%増加)を適用していた。旧コメント:
# ESR_M は BASE ×1.20 — 1柱告示(令和7年金融庁告示第74号)第59・60条の
# 罹患・障害リスク「健康事象発現時の一時金を提供する商品区分」・保険期間5年超・
# 日本の長期の割合(発生率 20%増加)を適用したレベルショック
SCENARIO_L = {"BASE": 0.010, "UP50": 0.015, "DN50": 0.005, "ICS_T": 0.000}
ICS_LEVEL_FACTOR = 1.125
ESR_MORTALITY_FACTOR = 1.125

# 給付項目(BNFT_Q)対応。死亡脱退用の全死因は BNFT_Q=0
CLAIM_DISEASES = {"cancer": 1, "heart_disease": 2, "cerebrovascular": 3}
MORT_DISEASE = "total"
SEX_CODE = {"male": "M", "female": "F"}

# fit 対象の年齢帯(5 歳階級の下限。バックテストと同じ 20–89 歳 14 区分)
AGE_LOWS = list(range(20, 90, 5))

BASE_CONFIG = ScaleBBConfig(
    long_term_rate=SCENARIO_L["BASE"],
    convergence_year=2035,
    last_observed_year=LAST_OBSERVED,
    lam_row=40.0,
    lam_col=20.0,  # [FIX 2026-09-02] backtest と同じ設定 (暦年グリッド化に伴い 40 → 20、§3.2.3)
    diff_order=2,
    age_taper_start=90,
    age_taper_end=120,
    horizon_year=HORIZON_YEAR,
)


def load_matrix(panel: pd.DataFrame, disease: str, sex: str) -> tuple[np.ndarray, list[int]]:
    """パネルから (年齢帯 × 観測年) の率行列を作る。欠測は NaN(重み 0 扱い)。"""
    sub = panel[(panel["disease_id"] == disease) & (panel["sex"] == sex)]
    pivot = sub.pivot_table(index="age_low", columns="year", values="rate_per_100k")
    years = sorted(pivot.columns)
    pivot = pivot.reindex(index=AGE_LOWS, columns=years)
    return pivot.to_numpy(dtype=float), years


def load_death_weights(panel: pd.DataFrame, disease: str, sex: str, years: list[int]) -> np.ndarray:
    """[ADD 2026-09-30] 死亡数の行列 (load_matrix と同じ形)。BEL_DEMO_VARIANT=deathweight の重みに使う。"""
    sub = panel[(panel["disease_id"] == disease) & (panel["sex"] == sex)]
    pivot = sub.pivot_table(index="age_low", columns="year", values="deaths")
    return pivot.reindex(index=AGE_LOWS, columns=years).to_numpy(dtype=float)


def band_index(attained_age: int) -> int:
    """到達年齢 → 年齢帯(5 歳階級)の行インデックス。"""
    low = min(85, (attained_age // 5) * 5)
    return AGE_LOWS.index(low)


def diagonal_records(surface: np.ndarray, proj_years: np.ndarray,
                     scn: str, bnft_q: int, gndr: str) -> list[dict]:
    """世代対角線 rate[dur] = m(x0+dur, 2026+dur) を per-100k → 小数で展開。"""
    recs = []
    year_idx = {int(y): k for k, y in enumerate(proj_years)}
    for x0 in ISSUE_AGES:
        for dur in range(MATURITY_AGE - x0):
            attained = x0 + dur
            year = ISSUE_YEAR + dur
            rate = surface[band_index(attained), year_idx[year]] / 100_000.0
            recs.append({
                "SCN_CD": scn, "BNFT_Q": bnft_q, "GNDR_CD": gndr,
                "ISSUE_AGE": x0, "DUR": dur, "ASSM_RT": rate,
            })
    return recs


def main() -> None:
    t0 = time.perf_counter()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    panel = pd.read_csv(PANEL_CSV)

    claim_recs: list[dict] = []
    mort_recs: list[dict] = []

    targets = [(d, s) for d in list(CLAIM_DISEASES) + [MORT_DISEASE] for s in SEX_CODE]
    for disease, sex in targets:
        mat, years = load_matrix(panel, disease, sex)
        weight = load_death_weights(panel, disease, sex, years) if VARIANT == "deathweight" else None
        fit = fit_scale_bb(mat, AGE_LOWS, years, config=BASE_CONFIG, weight=weight)

        # Phase 2 のみシナリオ別に再実行(全死因は BASE のみ)
        scenarios = SCENARIO_L if disease in CLAIM_DISEASES else {"BASE": SCENARIO_L["BASE"]}
        surfaces: dict[str, np.ndarray] = {}
        for scn, L in scenarios.items():
            fit.config = replace(BASE_CONFIG, long_term_rate=L)
            project_scale_bb(fit, base_year=LAST_OBSERVED)
            surfaces[scn] = fit.rate_projected.copy()
        proj_years = fit.projection_years
        if disease in CLAIM_DISEASES:
            # ICS_C: ICS_T の率を一律 ×1.125(レベルショック合成)
            surfaces["ICS_C"] = surfaces["ICS_T"] * ICS_LEVEL_FACTOR
            # ESR_M: BASE の率を一律 ×1.125(告示第56条 死亡リスクストレス)
            surfaces["ESR_M"] = surfaces["BASE"] * ESR_MORTALITY_FACTOR

        for scn, surface in surfaces.items():
            pd.DataFrame(surface, index=AGE_LOWS, columns=proj_years).to_csv(
                OUT_DIR / f"rate_surface_{disease}_{sex}_{scn}.csv",
                index_label="age_low",
            )
            if disease in CLAIM_DISEASES:
                claim_recs += diagonal_records(
                    surface, proj_years, scn, CLAIM_DISEASES[disease], SEX_CODE[sex])
            else:
                mort_recs += diagonal_records(surface, proj_years, scn, 0, SEX_CODE[sex])

    claims = pd.DataFrame(claim_recs)
    morts = pd.DataFrame(mort_recs)

    # --- 受入チェック ------------------------------------------------------
    n_dur = sum(MATURITY_AGE - x0 for x0 in ISSUE_AGES)  # 60+50+40+30 = 180
    assert len(claims) == 6 * 3 * 2 * n_dur, f"クレーム率の件数不一致: {len(claims)}"
    assert len(morts) == 2 * n_dur, f"死亡率の件数不一致: {len(morts)}"
    for df, name in [(claims, "claim"), (morts, "mortality")]:
        assert df["ASSM_RT"].notna().all(), f"{name}: 欠損あり"
        assert ((df["ASSM_RT"] > 0) & (df["ASSM_RT"] < 1)).all(), f"{name}: 率が (0,1) の範囲外"

    # L 単調性: 同一キーで UP50 < BASE < DN50 < ICS_T < ICS_C(改善加速ほど将来率が低い)
    wide = claims.pivot_table(index=["BNFT_Q", "GNDR_CD", "ISSUE_AGE", "DUR"],
                              columns="SCN_CD", values="ASSM_RT")
    order = ["UP50", "BASE", "DN50", "ICS_T", "ICS_C"]
    for lo, hi in zip(order[:-1], order[1:]):
        bad = (wide[lo] >= wide[hi]).sum()
        assert bad == 0, f"単調性違反: {lo} >= {hi} が {bad} 件"
    # ESR_M は BASE の一律 1.125 倍(構成上の恒等式)
    assert np.allclose(wide["ESR_M"], wide["BASE"] * ESR_MORTALITY_FACTOR), "ESR_M ≠ BASE×1.125"

    claims.to_csv(OUT_DIR / "scn_claim_rates.csv", index=False)
    morts.to_csv(OUT_DIR / "scn_mortality_rates.csv", index=False)

    elapsed = time.perf_counter() - t0
    print(f"OK: scn_claim_rates.csv {len(claims)} 行 / scn_mortality_rates.csv {len(morts)} 行")
    print(f"受入チェック合格(欠損なし・範囲内・L 単調性)。所要 {elapsed:.1f} 秒")


if __name__ == "__main__":
    main()
