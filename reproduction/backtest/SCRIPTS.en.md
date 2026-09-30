[日本語](SCRIPTS.md) | **English**

# SCRIPTS — What Each backtest Script Does

*English translation of [SCRIPTS.md](SCRIPTS.md) (as of 2026-08-06). If the versions disagree, the Japanese version is authoritative.*

This document explains the **processing performed** by each executable script bundled in `reproduction/backtest/` (1 shell script + 8 Python scripts), from the viewpoint of inputs, processing, and outputs. For the package's overall role, quickstart, and expected reference numbers, see [README.en.md](README.en.md); for the detailed per-file design documents (down to function specifications and output column definitions), see [docs/](docs/README.en.md).

## Overall processing flow

```
data/raw/5-15_*.csv ─┐
data/disease_estat_mapping.csv ─┴─► [1] build_panel.py
                                        │  data/disease_panel_mortality.csv
                                        ▼
              [2] run_backtest.py ──── [3] run_baselines.py     (×3 cutoffs: 2014/2021/2022)
                    │ validation_summary.csv     │ validation_summary_baseline.csv etc.
                    ▼                            ▼
              [4] compare_cutoffs.py       [5] compute_directional_accuracy.py
                    │ output/cutoff_comparison/   │ output/directional/
                    ▼                            ▼
              [6] make_calibration_recovery_figure.py   (fig. 6.3)
                    ▼
              [7] make_paper_figures.py   (→ ../../sections/figures/)
```

Each script simply does `import _paths` at the top, which resolves the bundled data and the algorithm core under `vendor/` (no dependency on any other directory).

---

## run_all.sh — one-shot reproduction driver

Shell script that runs the whole flow above in the correct order with the correct arguments.

- `set -euo pipefail` aborts immediately on any failure, and `cd "$(dirname "$0")"` moves into the script's own directory before running (so that `import _paths` resolves).
- The Python interpreter is chosen in priority order: environment variable `PY` → the repository root `.venv/bin/python` → `python3`.
- What it runs: ① `build_panel.py` → ② `run_backtest.py` and `run_baselines.py` for the three cutoffs (2014 → `output/`, 2021 → `output/cutoff_2021/`, 2022 → `output/cutoff_2022/`) → ③ `compare_cutoffs.py` → ④ `compute_directional_accuracy.py` → ⑤ `make_calibration_recovery_figure.py` → ⑥ `make_paper_figures.py`.

## _paths.py — self-contained path layer

The **single module that centralizes every path definition** used in the package. It contains no logic.

- Defines `RAW_VITAL_CSV` (the raw 5-15 CSV), `DISEASE_MAPPING`, `PANEL` (output of `build_panel.py` = input of all downstream scripts), and `OUTPUT_DIR`.
- Has the side effect of inserting `vendor/` into `sys.path` at import time, so that each script's `from experience_rate._scalebb_core.model import ...` resolves to the bundled core.
- The original scripts referenced `EAS/src` etc. relative to the repository root; that substitution is confined to this one module (the changed spots in each script are marked `# [REPRO]`).

## build_panel.py — [1] table 5-15 → disease panel (§3.1)

Builds the tidy panel `data/disease_panel_mortality.csv` — read by every downstream script — from the raw CSV of Vital Statistics table 5-15 (死因_性_5歳階級_年次 (cause of death × sex × 5-year age group × year), 1950–2024).

Processing:

1. Reads the raw CSV, strips the BOM from column names, and splits rows by `表章項目` (tabulated item) into deaths (死亡数) and death rates (死亡率).
2. Converts `性別` (sex: 総数/男/女) → `sex` slugs (total/male/female), `年齢(5歳階級)` (5-year age group) labels → `age_low` (0, 5, …, 100; "総数" (all ages) and "不詳" (unknown) are dropped), and `時間軸(年次)` (year) → integer `year`.
3. Maps `死因年次推移分類_code` (Hi codes) to the 8 disease slugs (cancer, diabetes, hypertensive, heart_disease, cerebrovascular, liver, kidney, total) via the `DISEASE_TO_HICODE` dict at the top of the script. Note that because of the 2017 classification revision, cancer and hypertensive are stored for the full period under the 2017-revision codes (`Hi022017` / `Hi042017`). Ischemic heart disease (heart_ischemic) does not exist in the table 5-15 classification and is excluded.
4. Joins rates and deaths on `(disease_id, sex, year, age_low)` and writes a long-format table with `rate_per_100k` and `deaths` columns (8 diseases × 3 sexes × 75 years × 21 age groups).
5. Also writes `data/panel_summary.csv`, a per-disease/sex summary of row/year/age counts, for sanity checking.

The first checkpoint of a correct reproduction is that this output matches the bundled reference file `data/prebuilt_disease_panel_mortality.csv`.

## run_backtest.py — [2] ScaleBB fit/project + validation (§3.2)

Reads the panel and, per disease × sex, fits and projects with the vendored Scale BB core (eqs. 3.1–3.6), then compares against actuals over the validation window.

CLI arguments: `--train-cutoff` (default 2014), `--validation-end` (default 2024), `--base-level` (level from which the projection starts: `observed` default / `mean_obs` / `smoothed`; [ADD 2026-09-03] paper §3.2.2 eq. 3.6 and §5.4), `--base-obs-points` (points for `mean_obs`, default 3), `--output-subdir (switches between `output/` itself and `output/cutoff_*/`).

Processing:

1. **Matrix construction** — `build_matrix()` pivots the data for the target disease/sex, ages 20–89, years ≤ cutoff, into an age × year rate matrix.
2. **fit/project** — calls `fit_scale_bb()` → `project_scale_bb()` with a `ScaleBBConfig` whose hyperparameters equal the EAS defaults: long-term improvement rate L = +1%, convergence year P = 2035, λ_row = λ_col = 40, 2nd-order differences, taper from age 90.
3. **Fit table** — writes observed (`observed_train`), smoothed (`smoothed`), and projected (`projected`) values, distinguished by a `kind` column, to the long-format `tables/fit_long.csv`.
4. **Validation table** — matches projections against actuals in the validation years and computes `error` (predicted − actual), `rel_error`, and `abs_rel_error` into `tables/validation_long.csv`. Cells with zero actuals get NaN relative errors.
5. **Aggregation** — `summarize()` writes per-disease/sex MAPE (mean of `abs_rel_error` over cells with actual > 0, ×100), RMSE, bias (mean `error`), and mean relative bias to `tables/validation_summary.csv`; `summarize_per_year()` writes the per-year breakdown to `tables/validation_by_year.csv`.
6. **Figures** — for sex=total, writes trajectory plots at representative ages (40/60/75) of observed/smoothed/projected/actual rates, `figures/<disease>_<sex>_trajectory.png` (log scale), and per-disease MAPE/bias trends `figures/overall_mape_bias_by_year.png`.

## run_baselines.py — [3] non-ScaleBB baselines (§3.3.1)

Runs three baseline methods under the identical backtest setup and writes artifacts directly comparable with ScaleBB.

The three methods (each predicting independently per age group):

- `naive_last` — holds the observed rate at the cutoff year flat over all validation years.
- `mean_3pts` — holds the mean of the last three observation points flat.
- `loglin_trend` — OLS of log(rate) on year over the last `--trend-window` years up to the cutoff (default 15), then exponential extrapolation (ages with fewer than 3 positive observations get NaN, i.e. no prediction).

CLI arguments: the same three as `run_backtest.py` plus `--trend-window`.

Processing: builds a long table over method × disease × sex × age × year, then aggregates MAPE/RMSE/bias with exactly the same definitions as `run_backtest.py` (`validation_long_baseline.csv` / `validation_summary_baseline.csv`). It then **reads the previously generated** ScaleBB outputs `validation_summary.csv` and `validation_by_year.csv`, merges them in, and writes the method-comparison tables (`method_comparison_summary.csv`; `method_comparison_MAPE_wide.csv`, a wide MAPE table with delta-vs-ScaleBB columns; `method_comparison_by_year.csv`) and two comparison figures (`baseline_vs_scalebb_mape.png`, `method_comparison_by_year.png`). Because of this, **it must run after `run_backtest.py` for the same cutoff**.

## compute_directional_accuracy.py — [4] directional accuracy DA (§3.3.2, eqs. 3.9–3.10)

Reads the existing artifacts of the three cutoffs (`fit_long.csv`, `validation_long.csv`, `validation_long_baseline.csv`) and computes the **directional accuracy** of all methods. No CLI arguments; the cutoff-to-subdirectory mapping is fixed in the `CUTOFFS` constant inside the script.

Processing:

1. For each cutoff, takes the observed rate at the cutoff year from `fit_long.csv` (the change baseline `rate_at_cutoff`) and merges in the predictions and actuals of ScaleBB and the three baselines.
2. Per cell (disease × sex × age × year), computes `actual_change = actual − rate_at_cutoff` and `predicted_change = predicted − rate_at_cutoff`; a match means the signs agree. **Cells with zero actual change are excluded (ambiguous truth).** Cells with zero predicted change (all cells of `naive_last`, by construction) **count as misses** — a method carrying no directional signal scoring DA = 0% is the intended behavior.
3. Writes the cell-level table `directional_long.csv`, the cutoff × method × disease × sex summary `directional_summary.csv` (including DA%, evaluable-cell counts, and the share of flat predictions `flat_pred_pct`), and the sex=total extract `directional_summary_total.csv` under `output/directional/tables/`.
4. Writes three figures — ScaleBB DA bars per cutoff, a 4-methods × diseases × 3-cutoffs comparison, and a head-to-head ScaleBB vs `loglin_trend` (the strongest baseline with an explicit directional signal) — under `output/directional/figures/`, each with a 50% (coin-flip) reference line.

## compare_cutoffs.py — [5] cross-cutoff comparison (§4)

Reads `validation_summary.csv` and `method_comparison_MAPE_wide.csv` from the three cutoff runs and writes side-by-side comparison tables and figures to `output/cutoff_comparison/`. No CLI arguments.

Processing:

1. Horizontally merges ScaleBB's MAPE/RMSE/bias with cutoff-suffixed columns and adds inter-cutoff MAPE delta columns (2021−2014, 2022−2014, 2022−2021), writing `scalebb_cutoff_comparison.csv`.
2. Writes `method_cutoff_comparison.csv`, the MAPE of all methods merged across cutoffs.
3. Three figures — ScaleBB MAPE bars per cutoff, a faceted 4-methods × 3-cutoffs figure, and the "ScaleBB − best baseline" MAPE gap figure (positive = ScaleBB worse; the companion table `scalebb_minus_best_baseline_gap.csv` is also written).

## make_calibration_recovery_figure.py — [6] recalibration experiment (§6.5, fig. 6.3)

Experiment script comparing the recovery of DA under 5 settings for the trend-reversal diseases **liver / hypertensive** (sex=total), which miss direction almost entirely at cutoff 2014. No CLI arguments.

- The 5 settings: ① 2014, default (L = +1%, P = 2035); ② 2014, L = 0%; ③ 2014, L = 0% and P = 2020; ④ 2021, default; ⑤ 2022, default. ②③ form the "calibration channel" (re-setting L and P per disease); ④⑤ form the "data channel" (letting the recent reversal enter the training data).
- **It does not depend on any existing artifacts under `output/`**: for all 5 settings it re-runs everything in-script, from fit/project through the DA computation (same definition as `compute_directional_accuracy.py`). The panel is read from `data/disease_panel_mortality.csv` (falling back to the bundled prebuilt file if absent).
- Outputs: `output/directional/tables/calibration_recovery.csv`, `output/directional/figures/calibration_recovery.png`, and the paper copy `../../sections/figures/fig_6_3_calibration_recovery.png` (committed to git).

## make_paper_figures.py — [7] generating and collecting the paper figures

Final step that assembles the figures referenced by the paper body into `../../sections/figures/` (committed to git). No CLI arguments. It does two jobs:

1. **New figures** (drawn directly from the panel; falls back to the prebuilt panel if not yet built)
   - Fig 3.1 `fig_3_1_input_panel_overview.png` — mortality-rate trends 1950–2024 of the 8 diseases at two representative ages (40 and 75), log scale.
   - Fig 3.2 `fig_3_2_smoothing_before_after.png` — before/after of the two-dimensional Whittaker–Henderson smoothing (eqs. 3.1–3.2), using heart_disease as the example, in year and age cross-sections.
   - Fig 3.3 `fig_3_3_blend_schematic.png` — a worked example of how observed improvement rates blend into the long-term rate L toward the convergence year P (eq. 3.5).
   - Fig 4.1 `fig_4_1_backtest_design.png` — schematic of the three cutoffs' training/validation windows around the COVID-19 period.
2. **Collection** — copies 7 backtest result figures from under `output/` (trajectories, MAPE/bias trends, gap figure, DA figures, etc.) to names `fig_5_1` through `fig_6_2` according to the `COLLECT` dict. Since `output/` is not under git, only the figures referenced by the paper body are moved here for committing. Missing figures produce a warning and are skipped.

## vendor/experience_rate/_scalebb_core/ — bundled algorithm core

An **unmodified copy** from EAS (`ValidationTools/EAS/src/experience_rate/_scalebb_core/`). The scripts in this package directly call only `ScaleBBConfig` / `fit_scale_bb` / `project_scale_bb` in `model.py` (§3.2, eqs. 3.1–3.6). `apc_model.py` (the APC extension, Appendix B) and the other modules are bundled for reference. For an explanation of the core implementation, see the EAS-side documents (`設計書.md` / `design_document.en.md`).

## compare_base_levels.py / compute_weighted_mape.py — [5b][5c] [ADD 2026-09-03]

`compare_base_levels.py` reads the main runs and the sensitivity runs `output/base_<level>_cutoff_<y>/` (produced by `run_all.sh` with `--base-level mean_obs|smoothed`) and writes `output/cutoff_comparison/tables/base_level_sensitivity.csv` (paper Table 5.5). `compute_weighted_mape.py` re-aggregates the validation cells with deaths weights (`deaths` column of the panel) and restricted to ages 40–89, and writes `weighted_mape.csv` (paper Table 5.4). `compute_rolling_origin.py` additionally writes `rolling_origin_conditional_da.csv` (accuracy by predicted direction) and `rolling_origin_winloss.csv`, and `compute_directional_accuracy.py` writes `directional_winloss.csv` (paper Table 6.3) and includes the `majority_direction` reference rule.
