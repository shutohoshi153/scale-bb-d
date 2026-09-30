#!/usr/bin/env bash
# 論文 §8（BEL 感応度デモ）と付録 A を一括再現し、最後に参照出力と突合する。
#
# 使い方:
#   cd reproduction/bel_demo && bash run_all.sh
#   bash run_all.sh --skip-check     # 突合を省略（自社データで回すとき）
#
# 前提:
#   - Python 3.10+、numpy / pandas / openpyxl / matplotlib（backtest/README の環境と同じ）
#   - 隣の backtest/ パッケージが存在すること（アルゴリズムコアと入力パネルを共用）
#   - 割引率パラメータ data/external/fsa_esr/esr_yield_curve_tool_20260331.xlsx が同梱されていること
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

SKIP_CHECK=0
[[ "${1:-}" == "--skip-check" ]] && SKIP_CHECK=1

run() { echo; echo "== $1 =="; python3 "$1"; }

run build_esr_discount_curve.py     # ⓪ ESR 割引カーブ（JPY・2026 年 3 月末、Smith-Wilson 補外）
run build_scenario_claim_rates.py   # ① Phase 1 フィット 1 回 → L 差し替えで 6 シナリオの率テーブル
run verify_pipeline_rates.py        # ② V1a: 率レベルの独立再導出・全件突合（許容 1e-12）
run calc_bel_standalone.py          # ③ BEL 計算（式 8.1–8.2）+ V2 単調性・V3 合成整合チェック
run aggregate_bel_results.py        # ④ 表 8.3 と図 8.1
run calc_esr_life_risk.py           # ⑤ 付録 A: 生保サブリスク → 相関統合 → MOCE → 保険負債

if [[ $SKIP_CHECK -eq 0 ]]; then
  echo; echo "== check_reference.py（参照出力との突合） =="
  python3 check_reference.py
fi
