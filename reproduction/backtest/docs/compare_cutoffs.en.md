[日本語](compare_cutoffs.md) | **English**

# Design Document — `compare_cutoffs.py` ([5] cross-cutoff comparison, §4)

*English translation of [compare_cutoffs.md](compare_cutoffs.md) (as of 2026-08-06). If the versions disagree, the Japanese version is authoritative.*

> For the cross-script overview see [../SCRIPTS.en.md](../SCRIPTS.en.md); for the package as a whole see [../README.en.md](../README.en.md).

## 1. Role and position

Compares the results of the three training cutoffs (2014 / 2021 / 2022) side by side, summarizing in tables and figures "how accuracy changes as the cutoff moves later (= recent data enters training and the forecast horizon shrinks)". `run_all.sh` step [3]. Corresponds to paper §4 (validation design) and §5.3.

**Precondition**: `run_backtest.py` and `run_baselines.py` have been run for all three cutoffs.

## 2. Inputs and outputs

**Inputs** (fixed by the `CUTOFFS` constant: 2014→`output/`, 2021→`output/cutoff_2021/`, 2022→`output/cutoff_2022/`)

| File | Use |
|---|---|
| `tables/validation_summary.csv` | ScaleBB MAPE / RMSE / bias / relative bias per disease × sex |
| `tables/method_comparison_MAPE_wide.csv` | Wide MAPE table of the 4 methods |

**Outputs** (under `output/cutoff_comparison/`)

| File | Content |
|---|---|
| `tables/scalebb_cutoff_comparison.csv` | ScaleBB's 4 metrics × 3 cutoffs merged horizontally (column suffixes `_2014` / `_2021` / `_2022`) + MAPE delta columns `delta_MAPE_2021_vs_2014` / `delta_MAPE_2022_vs_2014` / `delta_MAPE_2022_vs_2021` |
| `tables/method_cutoff_comparison.csv` | Long MAPE table of 4 methods × 3 cutoffs + inter-cutoff delta columns |
| `tables/scalebb_minus_best_baseline_gap.csv` | Per cutoff × disease: "ScaleBB MAPE − best baseline MAPE" (positive = ScaleBB worse) |
| `figures/scalebb_cutoff_comparison.png` | ScaleBB MAPE per disease, 3-cutoff grouped bars (sex=total) |
| `figures/method_cutoff_comparison.png` | MAPE of 4 methods × diseases, 3 panels (one per cutoff, sex=total) |
| `figures/scalebb_gap_vs_best_baseline.png` | Gap bar chart (with zero line; source of paper fig. 5.4) |

## 3. CLI arguments

None.

## 4. Processing flow (`main()`)

1. **ScaleBB cross table** — `load_scalebb()` reads each cutoff's `validation_summary.csv`, suffixes the metric columns with the cutoff, and merges successively on `(disease, sex)`. Adds the inter-cutoff MAPE delta columns, writes, and prints to stdout.
2. **Method cross table** — `load_wide()` reads each cutoff's wide MAPE table, `melt`s it to long form `(disease, sex, method, MAPE_<cutoff>)`, merges across cutoffs, adds delta columns, writes.
3. **Figure 1** — ScaleBB MAPE per disease for sex=total, 3-cutoff grouped bars (sorted by MAPE_2014 ascending).
4. **Figure 2** — faceted bar chart of methods × diseases × cutoffs (3 panels, shared y-axis).
5. **Figure 3 + companion table** — per cutoff × disease, computes the gap (pp) of ScaleBB MAPE minus the minimum MAPE among the 3 baselines, writing both the table and the bar chart.

## 5. Function specifications

### `load_scalebb(cutoff_subdir) -> DataFrame`
Returns `disease`, `sex` plus the 4 `KEEP` metric columns (`MAPE_pct`, `RMSE_per100k`, `bias_per100k`, `mean_rel_bias_pct`) from `validation_summary.csv` in the given subdirectory (`None` = directly under `output/`).

### `load_wide(cutoff_subdir) -> DataFrame`
Likewise reads `method_comparison_MAPE_wide.csv`.

## 6. Implementation notes

- The merges are inner joins, so a disease × sex missing in any cutoff drops out of the cross tables.
- The "best baseline" in the gap computation is chosen independently per cutoff × disease (it is not a fixed method).
- For the expected reference values (MAPE of cancer/total/hypertensive × 3 cutoffs), see "Expected key numbers" in [../README.en.md](../README.en.md).
