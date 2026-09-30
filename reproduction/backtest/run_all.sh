#!/usr/bin/env bash
# =============================================================================
# Paper_ICA2026 §3 再現ドライバ (ワンショット)
#
# §3 で記述した検証パイプラインを、生の人口動態統計 5-15 表から全成果物まで
# 一括再生成する。出力はすべて ./output/ 配下に生成される。
#
# 使い方:
#     bash run_all.sh                 # 既定 Python (python3) を使用
#     PY=/path/to/venv/bin/python bash run_all.sh   # 明示指定
#
# 依存: pandas / numpy / scipy / matplotlib (リポジトリ .venv に同梱済み)
# =============================================================================
set -euo pipefail

# スクリプト自身のディレクトリで実行 (import _paths を解決するため)
cd "$(dirname "$0")"

# Python 実行体: 環境変数 PY 優先 → リポジトリ .venv → python3
# (backtest/ は ICA/Paper_ICA2026/reproduction/backtest/ にあり、.venv はリポジトリルート)
if [[ -n "${PY:-}" ]]; then
    :
elif [[ -x "../../../../.venv/bin/python" ]]; then
    PY="../../../../.venv/bin/python"
else
    PY="python3"
fi
echo "[run_all] using Python: $($PY --version 2>&1)  ($PY)"

echo ""
echo "=== [1/5] パネル構築 (5-15 表 → data/disease_panel_mortality.csv) ==="
$PY build_panel.py

echo ""
echo "=== [2/5] ScaleBB fit/project + ベースライン (3 cutoff) ==="
# --- cutoff = 2014 (10年先予測 → output/) ---
$PY run_backtest.py --train-cutoff 2014 --validation-end 2024
$PY run_baselines.py --train-cutoff 2014 --validation-end 2024 --trend-window 15
# --- cutoff = 2021 (3年先予測 → output/cutoff_2021/) ---
$PY run_backtest.py --train-cutoff 2021 --validation-end 2024 --output-subdir cutoff_2021
$PY run_baselines.py --train-cutoff 2021 --validation-end 2024 --output-subdir cutoff_2021 --trend-window 15
# --- cutoff = 2022 (2年先予測 → output/cutoff_2022/) ---
$PY run_backtest.py --train-cutoff 2022 --validation-end 2024 --output-subdir cutoff_2022
$PY run_baselines.py --train-cutoff 2022 --validation-end 2024 --output-subdir cutoff_2022 --trend-window 15
# --- [ADD 2026-09-02] rolling-origin 2015-2020 (§4.2 / §6.2 の頑健性チェック → output/cutoff_<y>/) ---
for Y in 2015 2016 2017 2018 2019 2020; do
    $PY run_backtest.py --train-cutoff $Y --validation-end 2024 --output-subdir cutoff_$Y
    $PY run_baselines.py --train-cutoff $Y --validation-end 2024 --output-subdir cutoff_$Y --trend-window 15
done
# --- [ADD 2026-09-30] cutoff 2023 (1 年先 = 2024 のみ。固定ホライズン比較 §5.3 表 5.4 用 → output/cutoff_2023/) ---
$PY run_backtest.py --train-cutoff 2023 --validation-end 2024 --output-subdir cutoff_2023
$PY run_baselines.py --train-cutoff 2023 --validation-end 2024 --output-subdir cutoff_2023 --trend-window 15

# --- [ADD 2026-09-03] 投影起点の水準の感度 (§5, 査読 A-7 / B-4): mean_obs (直近 3 観測点平均) と smoothed (旧実装) ---
for Y in 2014 2021 2022; do
    for LVL in mean_obs smoothed; do
        $PY run_backtest.py --train-cutoff $Y --validation-end 2024 --output-subdir base_${LVL}_cutoff_$Y --base-level $LVL
    done
done

echo ""
echo "=== [3/5] cutoff 横断比較 (→ output/cutoff_comparison/) ==="
$PY compare_cutoffs.py
$PY compare_base_levels.py      # [ADD 2026-09-03] 起点水準の感度表 (§5)
$PY compute_weighted_mape.py    # [ADD 2026-09-03] 死亡数重み / 40 歳以上 MAPE (§5)
$PY compare_same_anchor.py      # [ADD 2026-09-30] 同一起点水準でのトレンド比較 (§5.3 表 5.5)
$PY compute_fixed_horizon.py    # [ADD 2026-09-30] 固定ホライズン (h = 1, 2, 3) の rolling-origin 比較 (§5.3 表 5.4)

echo ""
echo "=== [4/6] 方向性的中率 §3.4 (→ output/directional/) ==="
$PY compute_directional_accuracy.py
$PY compute_da_inference.py        # [ADD 2026-09-30] 二方向 (年齢 × 年) ブートストラップ区間と効果量 (§3.3, 表 6.1)

echo "=== [4b/6] rolling-origin 方向性的中率 §6.2 (→ output/directional/, 図 6.4) ==="
$PY compute_rolling_origin.py

echo ""
echo "=== [5/6] キャリブレーション回復図 §6.5 (→ output/directional/ + 図 6.3) ==="
$PY make_calibration_recovery_figure.py

echo ""
echo "=== [6/6] 論文掲載図の生成・収集 (→ output/paper_figures/。final/sections/figures/ へは手動コピー) ==="
$PY make_paper_figures.py

echo ""
echo "=== [記録・照合] 実行記録 (output/MANIFEST.json, reference_tables/) と論文の表との自動照合 ==="
$PY write_manifest.py
# [ADD 2026-09-30] 論文 §5・§6 の表 (final/sections_en_b1) と output/ の CSV を照合する。
# 公開リポジトリには final/ が無いため、無い場合は照合を飛ばす (失敗にはしない)。
if [[ -d "../../final/sections_en_b1" ]]; then
    $PY verify_paper_tables.py
else
    echo "[run_all] ../../final/sections_en_b1 が無いため verify_paper_tables.py を省略"
fi

echo ""
echo "[run_all] 完了。成果物は ./output/ (論文掲載図は ./output/paper_figures/) を参照。"
