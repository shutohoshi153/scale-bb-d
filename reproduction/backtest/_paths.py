"""再現パッケージの自己完結パス層.

目的:
    本パッケージ (Paper_ICA2026/reproduction/) を、リポジトリの他ディレクトリに
    依存せず単体で実行できるようにするための唯一のパス定義モジュール。
    元スクリプトはリポジトリルートを ``Path(__file__).parents[2]`` で辿り、
    ``EAS/src`` ・ ``ScaleBB_Research/data/raw`` ・ ``MedicalInsuranceProduct/`` を
    参照していたが、2026-07 のリポジトリ再編でこれらのパスは無効化された。
    本パッケージでは入力データ・アルゴリズムコアをすべて同梱し、ここで解決する。

査読者向けメモ:
    - 元スクリプトからの改変は「先頭のパスアンカー数行」のみ。アルゴリズム・集計・
      作図ロジックは一切変更していない (差分は ``git diff`` で追跡可能)。
    - ``import _paths`` した時点で、同梱の ``vendor/`` が ``sys.path`` に載り、
      ``from experience_rate._scalebb_core.model import ...`` がそのまま解決される。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# このファイル (reproduction/) を全パスのアンカーにする
HERE = Path(__file__).resolve().parent

# --- 入力データ (同梱) ---------------------------------------------------
DATA_DIR = HERE / "data"
RAW_VITAL_CSV = (
    DATA_DIR / "raw"
    / "5-15_死因_性_5歳階級_年次_死亡数率__0003411659.csv"
)
DISEASE_MAPPING = DATA_DIR / "disease_estat_mapping.csv"

# build_panel.py の出力先 = 後段スクリプトが読む PANEL
PANEL = DATA_DIR / "disease_panel_mortality.csv"
# [ADD 2026-09-30] 自社データでの検証用: 環境変数 SCALEBB_PANEL で入力パネルを差し替える
# (列仕様は同じ: disease_id, sex, year, age_low, rate_per_100k, deaths)。run_own_data.py が設定する。
if os.environ.get("SCALEBB_PANEL"):
    PANEL = Path(os.environ["SCALEBB_PANEL"]).expanduser().resolve()

# --- 出力 ----------------------------------------------------------------
OUTPUT_DIR = HERE / "output"

# --- 同梱アルゴリズムコア (experience_rate._scalebb_core) -----------------
VENDOR_DIR = HERE / "vendor"
if str(VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(VENDOR_DIR))
