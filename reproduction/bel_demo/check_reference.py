#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""参照出力との突合（再現パッケージ bel_demo の受入テスト）。

run_all.sh の最後に呼ばれ、再生成した結果が同梱の参照出力と一致することを確認する。

参照出力ディレクトリ（--reference-dir、既定 reference_output_20260930/）[ADD 2026-09-02]:
    reference_output_20260930/  2026-09-30 修正後（死因別死亡給付としての評価: 3 死因の脱退を 1 回だけ数える、ESR_M = 死亡率 +12.5%）の合格済み結果。
    reference_output_20260903/  2026-09-03 修正後（投影起点を観測率に変更、コア base_level="observed"）の合格済み結果。
    reference_output_20260902/  2026-09-02 修正後（平滑化グリッド annual_grid・lam_col=20、投影起点は平滑化率）の結果。現行コードでは一致しない。
                                論文 §8・付録 A の現行数値の元。
    reference_output/           修正前（2026-08 時点、共著者共有リポジトリと同一）のスナップショット。
                                現行コードでは一致しないため、履歴比較にのみ使う。

判定:
    - 数値列は相対誤差 RTOL（既定 1e-9）以内、文字列列は完全一致
    - 行数・列名が違えば不合格
終了コード: 0 = 全ファイル合格 / 1 = いずれか不合格（差分の先頭を表示）

使い方:
    python3 check_reference.py            # 既定の許容誤差
    python3 check_reference.py --rtol 1e-6
    python3 check_reference.py --reference-dir reference_output   # 修正前スナップショットとの比較（不一致が正常）
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

from _paths import OUTPUT_DIR, PROCESSED_DIR, REFERENCE_DIR

# 突合対象: (再生成物のパス, 参照出力ファイル名)
TARGETS = [
    (PROCESSED_DIR / "esr_jpy_spot_curve_20260331.csv", "esr_jpy_spot_curve_20260331.csv"),
    (OUTPUT_DIR / "bel_by_mp_scenario.csv", "bel_by_mp_scenario.csv"),
    (OUTPUT_DIR / "bel_sensitivity_table.csv", "bel_sensitivity_table.csv"),
    (OUTPUT_DIR / "verify_bel_checks.csv", "verify_bel_checks.csv"),
    (OUTPUT_DIR / "esr_life_risk_summary.csv", "esr_life_risk_summary.csv"),
]


def compare(actual: pd.DataFrame, expected: pd.DataFrame, rtol: float) -> list[str]:
    """2 つの表を比較し、不一致の説明文を返す（空なら合格）。"""
    problems: list[str] = []
    if list(actual.columns) != list(expected.columns):
        return [f"列名が異なる: {list(actual.columns)} vs {list(expected.columns)}"]
    if len(actual) != len(expected):
        return [f"行数が異なる: {len(actual)} vs {len(expected)}"]
    for col in expected.columns:
        a, e = actual[col], expected[col]
        if pd.api.types.is_numeric_dtype(e):
            bad = ~np.isclose(a.astype(float), e.astype(float), rtol=rtol, atol=0.0, equal_nan=True)
        else:
            bad = a.fillna("").astype(str) != e.fillna("").astype(str)
        if bad.any():
            i = int(np.flatnonzero(bad)[0])
            problems.append(f"列 {col}: {int(bad.sum())} 件不一致（例: 行 {i}: {a.iloc[i]!r} vs {e.iloc[i]!r}）")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rtol", type=float, default=1e-9, help="数値列の相対許容誤差")
    ap.add_argument("--reference-dir", default="reference_output_20260930",
                    help="参照出力ディレクトリ（bel_demo/ からの相対名。既定 reference_output_20260930）")
    args = ap.parse_args()
    global REFERENCE_DIR
    REFERENCE_DIR = REFERENCE_DIR.parent / args.reference_dir  # [ADD 2026-09-02]
    print(f"[check_reference] reference dir = {REFERENCE_DIR.name}")

    ok = True
    for actual_path, ref_name in TARGETS:
        ref_path = REFERENCE_DIR / ref_name
        if not actual_path.exists():
            print(f"✗ {ref_name}: 再生成物がありません ({actual_path})"); ok = False; continue
        if not ref_path.exists():
            print(f"✗ {ref_name}: 参照出力がありません ({ref_path})"); ok = False; continue
        problems = compare(pd.read_csv(actual_path), pd.read_csv(ref_path), args.rtol)
        if problems:
            ok = False
            print(f"✗ {ref_name}")
            for p in problems:
                print(f"    {p}")
        else:
            print(f"✓ {ref_name}")
    print("\n参照出力と一致: 合格" if ok else "\n参照出力と不一致: 不合格")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
