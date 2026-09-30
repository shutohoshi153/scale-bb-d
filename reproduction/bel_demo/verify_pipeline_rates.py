#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""パイプライン検証 V1a — 率レベル・全件突合(BEL感応度デモ)。

【目的】
    検算用サーフェス rate_surface_*.csv から世代対角線と単位換算(per 100k → 小数)を
    本スクリプト内で独立に再導出し、scn_claim_rates.csv / scn_mortality_rates.csv の
    全レコードと突合する。作業指示書 §7 V1a 準拠(フォールバック運用のため、突合対象は
    DB 内 TBL_CLAIM_SCN ではなく CSV 出力)。

【検証式】expected = rate_surface[band(x0 + dur), 2026 + dur] / 100_000
          全 (SCN, BNFT_Q, GNDR, ISSUE_AGE, DUR) について差が 1e-12 以内

【出力】ScaleBB/Research/output/bel_demo/verify_pipeline_rates.csv
        (不一致レコードの一覧。0 件で合格。終了コード 0=合格 / 1=不合格)

【注意】build_scenario_claim_rates.py の関数は import しない(同一バグ共有の防止)。
        対角線抽出・年齢帯マッピング・単位換算はすべて本スクリプト内で独立に実装する。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# --- パス(再現パッケージ・自己完結。定義は _paths.py) ----------------------
from _paths import PROCESSED_DIR as DATA_DIR, OUTPUT_DIR as OUT_DIR  # noqa: E402

# --- 仕様定数(作業指示書 §2・§3 から独立に転記) ---------------------------
ISSUE_YEAR = 2026
MATURITY_AGE = 90
ISSUE_AGES = [30, 40, 50, 60]
TOL = 1e-12

# BNFT_Q → 疾病 ID(0 は死亡脱退用の全死因)
BNFT_TO_DISEASE = {0: "total", 1: "cancer", 2: "heart_disease", 3: "cerebrovascular"}
GNDR_TO_SEX = {"M": "male", "F": "female"}


def expected_rate(surface: pd.DataFrame, x0: int, dur: int) -> float:
    """サーフェス(行=age_low、列=年)から世代対角線の 1 点を独立に再導出する。"""
    attained = x0 + dur
    band_low = min(85, (attained // 5) * 5)   # 5 歳階級の下限(85+ は 85-89 帯)
    year = ISSUE_YEAR + dur
    return float(surface.at[band_low, str(year)]) / 100_000.0


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    records = pd.concat([
        pd.read_csv(DATA_DIR / "scn_claim_rates.csv"),
        pd.read_csv(DATA_DIR / "scn_mortality_rates.csv"),
    ], ignore_index=True)

    surfaces: dict[tuple[str, int, str], pd.DataFrame] = {}
    mismatches = []
    n_checked = 0
    for row in records.itertuples(index=False):
        key = (row.SCN_CD, row.BNFT_Q, row.GNDR_CD)
        if key not in surfaces:
            disease = BNFT_TO_DISEASE[row.BNFT_Q]
            sex = GNDR_TO_SEX[row.GNDR_CD]
            path = DATA_DIR / f"rate_surface_{disease}_{sex}_{row.SCN_CD}.csv"
            surfaces[key] = pd.read_csv(path).set_index("age_low")
        exp = expected_rate(surfaces[key], int(row.ISSUE_AGE), int(row.DUR))
        n_checked += 1
        if abs(exp - row.ASSM_RT) > TOL:
            mismatches.append({**row._asdict(), "EXPECTED": exp, "DIFF": exp - row.ASSM_RT})

    result = pd.DataFrame(mismatches)
    result.to_csv(OUT_DIR / "verify_pipeline_rates.csv", index=False)
    # 6 シナリオ(BASE/UP50/DN50/ICS_T/ICS_C/ESR_M)× 3 給付 + 全死因(BASE のみ)
    n_expected = (6 * 3 + 1) * 2 * sum(MATURITY_AGE - a for a in ISSUE_AGES)
    status = "合格" if (not mismatches and n_checked == n_expected) else "不合格"
    print(f"V1a {status}: 突合 {n_checked} 件(期待 {n_expected} 件)、不一致 {len(mismatches)} 件"
          f"(許容誤差 {TOL:g})")
    return 0 if status == "合格" else 1


if __name__ == "__main__":
    sys.exit(main())
