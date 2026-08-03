#!/usr/bin/env bash
# =============================================================================
# Paper §3 reproduction driver (one-shot)
#
# Regenerates the validation pipeline described in §3, from the raw vital
# statistics table 5-15 through to all artifacts. All outputs are written
# under ./output/.
#
# Usage:
#     bash run_all.sh                 # use default Python (python3)
#     PY=/path/to/venv/bin/python bash run_all.sh   # explicit interpreter
#
# Dependencies: Python 3.10+ with pandas / numpy / scipy / matplotlib
# =============================================================================
set -euo pipefail

# Run from this script's own directory (so that `import _paths` resolves)
cd "$(dirname "$0")"

# Python interpreter: env var PY if set, otherwise python3
if [[ -n "${PY:-}" ]]; then
    :
else
    PY="python3"
fi
echo "[run_all] using Python: $($PY --version 2>&1)  ($PY)"

echo ""
echo "=== [1/6] Build panel (table 5-15 -> data/disease_panel_mortality.csv) ==="
$PY build_panel.py

echo ""
echo "=== [2/6] ScaleBB fit/project + baselines (3 cutoffs) ==="
# --- cutoff = 2014 (10-year-ahead forecast -> output/) ---
$PY run_backtest.py --train-cutoff 2014 --validation-end 2024
$PY run_baselines.py --train-cutoff 2014 --validation-end 2024 --trend-window 15
# --- cutoff = 2021 (3-year-ahead forecast -> output/cutoff_2021/) ---
$PY run_backtest.py --train-cutoff 2021 --validation-end 2024 --output-subdir cutoff_2021
$PY run_baselines.py --train-cutoff 2021 --validation-end 2024 --output-subdir cutoff_2021 --trend-window 15
# --- cutoff = 2022 (2-year-ahead forecast -> output/cutoff_2022/) ---
$PY run_backtest.py --train-cutoff 2022 --validation-end 2024 --output-subdir cutoff_2022
$PY run_baselines.py --train-cutoff 2022 --validation-end 2024 --output-subdir cutoff_2022 --trend-window 15

echo ""
echo "=== [3/6] Cross-cutoff comparison (-> output/cutoff_comparison/) ==="
$PY compare_cutoffs.py

echo ""
echo "=== [4/6] Directional accuracy §3.4 (-> output/directional/) ==="
$PY compute_directional_accuracy.py

echo ""
echo "=== [5/6] Calibration-recovery figure §6.5 (-> output/directional/ + Figure 6.3) ==="
$PY make_calibration_recovery_figure.py

echo ""
echo "=== [6/6] Generate & collect paper figures (-> ../../figures/) ==="
$PY make_paper_figures.py

echo ""
echo "[run_all] Done. See ./output/ for artifacts (paper figures in ../../figures/)."
