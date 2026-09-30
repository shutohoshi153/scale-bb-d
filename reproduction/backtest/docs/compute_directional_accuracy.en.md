[日本語](compute_directional_accuracy.md) | **English**

# Design Document — `compute_directional_accuracy.py` ([4] directional accuracy DA, §3.4.2 eqs. 3.11–3.12)

*English translation of [compute_directional_accuracy.md](compute_directional_accuracy.md) (as of 2026-08-06). If the versions disagree, the Japanese version is authoritative.*

> For the cross-script overview see [../SCRIPTS.en.md](../SCRIPTS.en.md); for the package as a whole see [../README.en.md](../README.en.md).

## 1. Role and position

Reads the existing artifacts of the three cutoffs and computes the **directional accuracy (DA: the share of cells where the sign of change was predicted correctly)** for ScaleBB and the three baselines. `run_all.sh` step [4]. The results underpin the discussion in paper §6.

**Precondition**: `run_backtest.py` and `run_baselines.py` have been run for all three cutoffs.

## 2. Definition of DA (eqs. 3.11–3.12)

Per cell (disease × sex × age × validation year), relative to the **observed rate at the cutoff year**:

```
actual_change    = actual_rate    − rate_at_cutoff
predicted_change = predicted_rate − rate_at_cutoff
match            = sign(actual_change) == sign(predicted_change)
```

- **Excluded from evaluation**: cells with `sign(actual_change) == 0` (the true direction is ambiguous; tracked by the `evaluable` flag).
- **Counted as misses**: cells with `sign(predicted_change) == 0`. For `naive_last` every cell falls in this category by construction, so its DA = 0% — the design intent is to make explicit that "a no-change prediction carries no directional information".
- DA% = matched cells ÷ evaluable cells × 100.

## 3. Inputs and outputs

**Inputs** (cutoff → source directory fixed in the `CUTOFFS` constant: 2014→`output/`, 2021→`output/cutoff_2021/`, 2022→`output/cutoff_2022/`)

| File | Use |
|---|---|
| `tables/fit_long.csv` | The baseline value `rate_at_cutoff` is taken from rows with `kind == "observed_train"` and `year == cutoff` |
| `tables/validation_long.csv` | ScaleBB predicted-vs-actual (tagged method=`scalebb`) |
| `tables/validation_long_baseline.csv` | Predicted-vs-actual of the three baselines |

**Outputs** (under `output/directional/`)

| File | Content |
|---|---|
| `tables/directional_long.csv` | Cell level, including `actual_change`, `predicted_change`, `actual_sign`, `pred_sign`, `match`, `evaluable`, `cutoff` |
| `tables/directional_summary.csv` | Per cutoff × method × disease × sex: `n_cells_evaluable`, `n_matches`, `dir_acc_pct`, `n_flat_preds`, `flat_pred_pct` |
| `tables/directional_summary_total.csv` | The above restricted to sex=total |
| `figures/scalebb_directional_per_cutoff.png` | ScaleBB DA bars per disease × cutoff |
| `figures/method_directional_comparison.png` | DA of 4 methods × diseases, 3 panels (one per cutoff) |
| `figures/scalebb_vs_loglin_directional.png` | Head-to-head ScaleBB vs `loglin_trend` (3 panels) |

All figures carry a dashed 50% (coin-flip) reference line, y-axis 0–100%.

## 4. CLI arguments

None. The cutoff-to-subdirectory mapping and figure titles are fixed in the `CUTOFFS` constant at the top of the script (a list of `(cutoff, subdir, title)`).

## 5. Processing flow (`main()`)

1. Calls `compute_directional()` per cutoff, concatenates the cell-level tables, and writes `directional_long.csv`.
2. Aggregates via `summarize()` per cutoff × method × disease × sex, writing `directional_summary.csv` and the sex=total extract.
3. Draws the three figures (below).
4. Prints the sex=total DA pivoted as disease × (cutoff, method) to stdout.

## 6. Function specifications

### `load_observed_at_cutoff(subdir, cutoff) -> DataFrame`
Extracts the observed values of the cutoff year from `fit_long.csv` and returns them renamed to `rate_at_cutoff` (keys: disease, sex, age_low).

### `load_val(subdir) -> DataFrame`
Aligns the ScaleBB `validation_long.csv` (tagged method=`scalebb`) and the baseline `validation_long_baseline.csv` to common columns and concatenates them.

### `compute_directional(cutoff, subdir) -> DataFrame`
Left-joins the baseline values onto the predicted-vs-actual table and computes changes, signs, `match`, and `evaluable`. Rows missing any of `actual_change` / `predicted_change` / `rate_at_cutoff` are dropped.

### `summarize(long_df) -> DataFrame`
Groups only rows with `evaluable == True` per cutoff × method × disease × sex and aggregates DA% together with the count and share of flat-prediction cells (`n_flat_preds` / `flat_pred_pct`).

## 7. Design intent of the figures

- **Figure 1** (ScaleBB × cutoff): shows the "data channel" — DA of the trend-reversal diseases recovering as the cutoff moves later.
- **Figure 2** (4-method comparison): an overview of which methods carry a directional signal, including `naive_last` at DA=0%; the figure title states the reason for the 0%.
- **Figure 3** (vs `loglin_trend`): a fair head-to-head against the strongest baseline that carries an explicit directional signal.

## 8. Implementation notes

- The denominator of all aggregation and plotting is always the `evaluable` cells. `directional_long.csv` retains the excluded cells too (`evaluable=False`), so filter when doing secondary analysis.
- `rate_at_cutoff` uses the **observed** value (`observed_train`), not the smoothed value. The DA computation in `make_calibration_recovery_figure.py` is aligned to this same definition.
