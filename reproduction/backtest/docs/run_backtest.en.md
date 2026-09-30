[日本語](run_backtest.md) | **English**

# Design Document — `run_backtest.py` ([2] ScaleBB fit/project + validation, §3.2)

*English translation of [run_backtest.md](run_backtest.md) (as of 2026-08-06). If the versions disagree, the Japanese version is authoritative.*

> For the cross-script overview see [../SCRIPTS.en.md](../SCRIPTS.en.md); for the package as a whole see [../README.en.md](../README.en.md).

## 1. Role and position

Reads the disease panel and, per disease × sex, runs "train up to the cutoff year → project into the validation window" with the bundled Scale BB core (eqs. 3.1–3.6), then matches against actuals and aggregates accuracy metrics. As `run_all.sh` step [2] it is **executed three times, once per cutoff (2014/2021/2022)**, writing artifacts to `output/`, `output/cutoff_2021/`, and `output/cutoff_2022/` respectively.

## 2. Inputs and outputs

**Inputs**: `_paths.PANEL` (output of `build_panel.py`) and `experience_rate._scalebb_core.model` from `vendor/`.

**Outputs** (under `output[/<subdir>]/`)

| File | Content |
|---|---|
| `tables/fit_long.csv` | Long table of observed / smoothed / projected values. Columns: `disease`, `sex`, `age_low`, `year`, `kind` (`observed_train` / `smoothed` / `projected`), `rate_per_100k` |
| `tables/validation_long.csv` | Cell-level predicted-vs-actual. Columns: `disease`, `sex`, `age_low`, `year`, `actual_rate_per_100k`, `predicted_rate_per_100k`, `error`, `rel_error`, `abs_rel_error` |
| `tables/validation_summary.csv` | Per disease × sex aggregation. Columns: `n_cells`, `MAPE_pct`, `RMSE_per100k`, `bias_per100k`, `mean_rel_bias_pct`, `MAPE_<first/mid/last year>`, `RMSE_<first/last year>` |
| `tables/validation_by_year.csv` | Per disease × sex × year aggregation (same metrics) |
| `figures/<disease>_<sex>_trajectory.png` | Trajectory plot at representative ages (generated for sex=total only) |
| `figures/overall_mape_bias_by_year.png` | Per-disease MAPE / relative-bias trends by year (sex=total) |

## 3. CLI arguments

| Argument | Default | Meaning |
|---|---|---|
| `--train-cutoff` | 2014 | Last year used for training |
| `--validation-end` | 2024 | Last year of the validation window (validation years = cutoff+1 … this year) |
| `--output-subdir` | `""` | Subdirectory name under `output/`. Empty = directly under `output/` (default behaviour for cutoff 2014) |

The arguments are applied in `main()` to module-level mutable globals (`TRAIN_CUTOFF`, `VALIDATION_YEARS`, `OUT_TABLES`, `OUT_FIGS`).

## 4. Processing flow (`main()`)

1. Parses arguments, creates the output directories, loads the panel.
2. Loops over all diseases in the panel × sexes {total, male, female} and calls `run_one()` (combinations without data are skipped). Only for sex=total does it draw the trajectory figure via `make_trajectory_plot()`.
3. Concatenates the fit and validation tables of all combinations into `fit_long.csv` / `validation_long.csv`.
4. Writes `summarize()` → `validation_summary.csv` and `summarize_per_year()` → `validation_by_year.csv`, then draws the yearly-trend figure via `make_overall_plots()`.

## 5. Function specifications

### `build_matrix(df, *, disease, sex, year_max) -> (ages, years, rates)`
Pivots (`pivot_table`, mean) the rows for the target disease/sex, ages 20–89 (`AGE_MIN`/`AGE_MAX`), `year <= year_max` into age × year, and returns the age array, year array, and rate matrix (NumPy).

### `run_one(df, *, disease, sex) -> (fit_df, val_df)`
Main processing for one disease × sex.

1. Builds the training matrix via `build_matrix()` (returns empty DataFrames — skipped — if empty or all non-finite).
2. Builds `ScaleBBConfig(last_observed_year=TRAIN_CUTOFF, horizon_year=max(VALIDATION_YEARS), **SCALE_BB_CONFIG)` and runs `fit_scale_bb()` → `project_scale_bb(base_year=TRAIN_CUTOFF)`.
3. **Fit table**: expands observed training values (`observed_train`), smoothed values (`smoothed`), and post-cutoff projections (`projected`) into long format with a `kind` column.
4. **Validation table**: pivots the actuals of the validation years, matches them against projections, and computes:
   - `error = predicted − actual`
   - `rel_error = error / actual`, with **NaN for cells where actual ≤ 0** (relative error undefined at zero)
   - `abs_rel_error = |rel_error|`

### `summarize(val_df) -> DataFrame`
Groups cells with both actual and predicted non-missing by disease × sex and aggregates:

| Metric | Definition |
|---|---|
| `MAPE_pct` | Mean of `abs_rel_error` over cells with actual > 0, × 100 (eq. 3.9) |
| `RMSE_per100k` | Square root of the mean squared error over all cells |
| `bias_per100k` | Mean of `error` (positive = over-prediction) |
| `mean_rel_bias_pct` | Mean of `rel_error` over cells with actual > 0, × 100 (eq. 3.10) |
| `MAPE_<year>` / `RMSE_<year>` | Per-year values at the first/middle/last validation year (RMSE: first/last). Column names are derived dynamically from the validation window |

### `summarize_per_year(val_df) -> DataFrame`
Aggregates the same metrics at disease × sex × **year** granularity (for trend analysis and plotting).

### `make_trajectory_plot(disease, sex, fit_df, val_df)`
Three panels at representative ages 40/60/75, overlaying observed (blue circles), smoothed (orange solid), projected (green dashed), and validation actuals (red ×) on a log scale, with a vertical dotted line at the cutoff year.

### `make_overall_plots(per_year)`
For sex=total, draws per-disease MAPE trends by year (left panel) and mean relative-bias trends (right panel, with a zero line).

## 6. Constants and configuration

**`SCALE_BB_CONFIG`** — hyperparameters identical to the EAS defaults in `config.yaml > scalebb_presets` (§3.2.3):

| Key | Value | Meaning |
|---|---|---|
| `long_term_rate` | 0.01 | Long-term improvement rate L = +1%/year |
| `convergence_year` | 2035 | Convergence year P |
| `lam_row` / `lam_col` | 40.0 / 40.0 | Whittaker–Henderson smoothing penalties (age / year direction) |
| `diff_order` | 2 | Difference order |
| `age_taper_start` / `age_taper_end` | 90 / 120 | Improvement-rate taper interval at high ages |

`AGE_MIN, AGE_MAX = 20, 89` — restricts to ages with non-trivial death rates and full mapping coverage.

## 7. Implementation notes

- MAPE and RMSE use different denominators (MAPE: only cells with actual > 0; RMSE: all non-missing cells).
- Figures are generated for sex=total only (male/female get tables only).
- matplotlib is pinned to the `Agg` backend (headless execution).
- The three cutoffs' artifacts are read downstream by `compare_cutoffs.py` and `compute_directional_accuracy.py`, so renaming files or columns propagates downstream.
