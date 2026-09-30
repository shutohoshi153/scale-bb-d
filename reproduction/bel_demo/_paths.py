"""再現パッケージ bel_demo の自己完結パス層（backtest/_paths.py と同型）.

目的:
    論文 §8（BEL 感応度デモ）と付録 A を、リポジトリの他ディレクトリに依存せず
    reproduction/ 配下だけで再実行できるようにするための唯一のパス定義モジュール。
    原本（ICA/ScaleBB/Research/scripts/bel_demo/）は ICA ルートを
    ``Path(__file__).parents[4]`` で辿り、EAS のソース・BackTest_2015_2024 のパネル・
    Research 配下のデータを参照していた。本パッケージでは
      - アルゴリズムコアと入力パネル → 隣の backtest/ パッケージに同梱済みのものを共用
      - 金融庁公表資料（イールド・カーブ作成ツール） → data/external/fsa_esr/ に同梱
    として、ここで解決する。

査読者・実務者向けメモ:
    - 原本からの改変は「先頭のパスアンカー数行」のみ（Paper_ICA2026_publish/package_bel_demo.sh
      が完全一致で置換）。計算ロジックは一切変更していない。
    - ``import _paths`` した時点で backtest/vendor/ が sys.path に載り、
      ``from experience_rate._scalebb_core.model import ...`` がそのまま解決される。
    - 自社データで回す場合は PANEL_CSV（死因別死亡率パネル）と XLSX（割引率パラメータ）を
      差し替えるだけでよい。列仕様は README を参照。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent           # reproduction/bel_demo/
BACKTEST = HERE.parent / "backtest"              # 隣の再現パッケージ（コア・パネルを共用）

# --- 入力（同梱 or backtest/ 共用） ------------------------------------------
# 死因別死亡率パネル（per 100k）。backtest/build_panel.py の出力と一致する事前生成物を使う。
PANEL_CSV = BACKTEST / "data" / "prebuilt_disease_panel_mortality.csv"
# 金融庁「イールド・カーブ作成ツール」（2026 年 3 月末版）。出典は data/external/fsa_esr/README.md
XLSX = HERE / "data" / "external" / "fsa_esr" / "esr_yield_curve_tool_20260331.xlsx"

# --- 中間生成物・出力（再生成物。git 追跡外） --------------------------------
PROCESSED_DIR = HERE / "data" / "processed"      # 割引カーブ・シナリオ別率・検算用サーフェス
OUTPUT_DIR = HERE / "output"                     # BEL・感応度表・図・付録 A

# [ADD 2026-09-30] 感度分析用の変種。環境変数 BEL_DEMO_VARIANT=deathweight で、Phase 1 の平滑化を
# 死亡数重み付きに替えた結果を別ディレクトリ (data/processed_deathweight/、output_deathweight/) に出力する
# (論文 §10 第 6 項、審査指摘 A-8)。未設定なら論文の主結果 (等重み) を従来の場所に出力する。
VARIANT = os.environ.get("BEL_DEMO_VARIANT", "").strip()
if VARIANT not in ("", "deathweight"):
    raise ValueError(f"unknown BEL_DEMO_VARIANT: {VARIANT!r} (use 'deathweight' or leave unset)")
if VARIANT:
    PROCESSED_DIR = HERE / "data" / f"processed_{VARIANT}"
    OUTPUT_DIR = HERE / f"output_{VARIANT}"
REFERENCE_DIR = HERE / "reference_output"        # 合格済みの参照結果（check_reference.py が突合）

for d in (PROCESSED_DIR, OUTPUT_DIR):
    d.mkdir(parents=True, exist_ok=True)

# --- 同梱アルゴリズムコア（backtest/vendor/experience_rate/_scalebb_core） -------
VENDOR_DIR = BACKTEST / "vendor"
if str(VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(VENDOR_DIR))
