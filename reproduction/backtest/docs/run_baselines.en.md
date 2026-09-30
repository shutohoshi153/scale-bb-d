[日本語](run_baselines.md) | **English**

# Design Document — `run_baselines.py` ([3] non-ScaleBB baselines, §3.4.1)

*English translation of [run_baselines.md](run_baselines.md) (as of 2026-08-06). If the versions disagree, the Japanese version is authoritative.*

> For the cross-script overview see [../SCRIPTS.en.md](../SCRIPTS.en.md); for the package as a whole see [../README.en.md](../README.en.md).

## 1. Role and position

Runs three baseline methods under the **identical backtest setup** as `run_backtest.py` (same panel, same age range, same cutoff, same validation years) and writes tables and figures directly comparable with ScaleBB. Within `run_all.sh` step [2] it runs **immediately after** `run_backtest.py` for each cutoff.

**Precondition**: the ScaleBB-side `validation_summary.csv` and `validation_by_year.csv` must already exist in the same output directory (they are read when building the method-comparison tables).

## 2. Baseline method definitions

Each method predicts independently per age group.

| method | Definition |
|---|---|
| `naive_last` | Holds the observed rate at the cutoff year flat over all validation years (predicted_t = observed_cutoff) |
| `mean_3pts` | Holds the `nanmean` of the last three observation points (by year order) flat over all validation years |
| `loglin_trend` | Simple OLS of log(rate) on year over the last `--trend-window` years up to the cutoff (default 15), extrapolated exponentially into the validation years |

For `loglin_trend`, ages with fewer than 3 positive finite observations get no coefficients; their predictions are NaN (= excluded from aggregation).

## 3. Inputs and outputs

**Inputs**: `_paths.PANEL`, plus the ScaleBB-side `tables/validation_summary.csv` and `tables/validation_by_year.csv` in the same output directory.

**Outputs** (under `output[/<subdir>]/`)

| File | Content |
|---|---|
| `tables/validation_long_baseline.csv` | Cell-level predicted-vs-actual per method × disease × sex × age × year (with `error`, `rel_error`, `abs_rel_error`) |
| `tables/validation_summary_baseline.csv` | MAPE / RMSE / bias / relative bias per method × disease × sex |
| `tables/method_comparison_summary.csv` | The above with ScaleBB (method=`scalebb`) concatenated in — a 4-method comparison |
| `tables/method_comparison_MAPE_wide.csv` | Wide MAPE table, (disease × sex) × method, plus `delta_<method>_minus_scalebb` columns |
| `tables/method_comparison_by_year.csv` | MAPE per method × disease × year for sex=total (including ScaleBB) |
| `figures/baseline_vs_scalebb_mape.png` | Per-disease 4-method MAPE bar chart (sex=total, sorted by ScaleBB MAPE ascending) |
| `figures/method_comparison_by_year.png` | Eight panels per disease, yearly MAPE trends with the 4 methods overlaid |

## 4. CLI arguments

| Argument | Default | Meaning |
|---|---|---|
| `--train-cutoff` | 2014 | Last training year |
| `--validation-end` | 2024 | Last validation year |
| `--output-subdir` | `""` | Subdirectory under `output/` |
| `--trend-window` | 15 | Number of years (cutoff inclusive) used for the `loglin_trend` fit. `TREND_WINDOW_START = cutoff − window + 1` |

## 5. Processing flow (`main()`)

1. Applies arguments to the mutable globals, creates the output directories, loads the panel.
2. For every disease × sex {total, male, female}, calls `run_baselines_for()` and accumulates the cell rows for the 3 methods.
3. `summarize()` attaches the error columns and aggregates per method × disease × sex, writing `validation_long_baseline.csv` / `validation_summary_baseline.csv`.
4. Reads the ScaleBB `validation_summary.csv`, concatenates it, and writes `method_comparison_summary.csv` and the wide MAPE table (with delta-vs-ScaleBB columns).
5. For sex=total, re-aggregates cell-level MAPE per method × disease × year, merges in the ScaleBB `validation_by_year.csv`, and writes `method_comparison_by_year.csv`.
6. Writes the two comparison figures and prints the sex=total wide MAPE table to stdout.

## 6. Function specifications

### `predict_naive_last(years_train, rates_train) -> (n_age,)`
Returns the column of the maximum year (the cutoff year) as is.

### `predict_mean_3pts(years_train, rates_train) -> (n_age,)`
`nanmean` of the last three columns after ordering years via `argsort`. Even with gaps in the observations, it uses "the three most recent observation points" (e.g. 2010, 2013, 2014).

### `predict_loglin(years_train, rates_train, *, window_start) -> (intercept, slope)`
Restricts to columns with `year >= window_start` and computes closed-form OLS coefficients of log(rate) on year per age. Ages with fewer than 3 valid observations (finite and positive), or with zero variance in year, remain NaN. Predictions are computed by broadcasting `exp(a + b·year)`.

### `build_panel_for(df, *, disease, sex) -> (ages, years_train, rates_train, val_actual)`
Pivots the training and validation windows separately; the validation side is `reindex`ed to the training side's age index and the validation years so the matrix shapes align.

### `make_validation_rows(method, disease, sex, ages, val_actual, predicted_per_year)`
Expands the (n_age × n_validation_years) prediction and actual matrices into cell-level long rows.

### `summarize(val_df) -> (summary, val_df_enriched)`
Attaches error columns with the **same definitions** as `run_backtest.py` (relative error NaN where actual ≤ 0) and aggregates MAPE / RMSE / bias / relative bias per method × disease × sex.

## 7. Implementation notes

- Keeping the metric definitions identical to `run_backtest.py` is a requirement of this script (fairness of comparison). If the definitions change, change both scripts together.
- Order dependency: running before `run_backtest.py` for the same cutoff fails when reading the ScaleBB summary files.
- `naive_last` / `mean_3pts` produce the same value for every validation year (flat predictions) and therefore structurally carry no directional signal in the directional-accuracy computation (see the design document of `compute_directional_accuracy.py`).
