[日本語](make_paper_figures.md) | **English**

# Design Document — `make_paper_figures.py` ([7] generating and collecting the paper figures)

*English translation of [make_paper_figures.md](make_paper_figures.md) (as of 2026-08-06). If the versions disagree, the Japanese version is authoritative.*

> For the cross-script overview see [../SCRIPTS.en.md](../SCRIPTS.en.md); for the package as a whole see [../README.en.md](../README.en.md).

## 1. Role and position

The final step (`run_all.sh` step [6]) that assembles the figures referenced by the paper body (`sections/`) into `../../sections/figures/` (**committed to git**). It does two jobs:

1. **New figures** — draws the 4 explanatory figures for §3 and §4 directly from the panel.
2. **Collection** — copies, under paper file names, the 7 backtest result figures referenced by §5 and §6 from under `output/` (not under git).

## 2. Inputs and outputs

**Inputs**: `data/disease_panel_mortality.csv` (falls back to the bundled `prebuilt_disease_panel_mortality.csv` if absent — the newly generated figures work even without building the panel), the core under `vendor/`, and the collected figures under `output/`.

**Outputs** (all in `../../sections/figures/`)

| File | Kind | Content |
|---|---|---|
| `fig_3_1_input_panel_overview.png` | generated | Input panel overview (§3.1) |
| `fig_3_2_smoothing_before_after.png` | generated | Smoothing before/after (§3.2.1, eqs. 3.1–3.2) |
| `fig_3_3_blend_schematic.png` | generated | Worked example of improvement-rate blending (§3.2.2, eq. 3.5) |
| `fig_4_1_backtest_design.png` | generated | Schematic of the 3-cutoff design (§4.2) |
| `fig_5_1_overall_mape_bias_by_year.png` | collected | ← `output/figures/overall_mape_bias_by_year.png` |
| `fig_5_2_heart_disease_total_trajectory.png` | collected | ← `output/figures/heart_disease_total_trajectory.png` |
| `fig_5_3_cancer_total_trajectory.png` | collected | ← `output/figures/cancer_total_trajectory.png` |
| `fig_5_4_scalebb_gap_vs_best_baseline.png` | collected | ← `output/cutoff_comparison/figures/…` |
| `fig_5_5_scalebb_cutoff_comparison.png` | collected | ← `output/cutoff_comparison/figures/…` |
| `fig_6_1_scalebb_directional_per_cutoff.png` | collected | ← `output/directional/figures/…` |
| `fig_6_2_scalebb_vs_loglin_directional.png` | collected | ← `output/directional/figures/…` |

Figure 6.3 alone is generated directly by `make_calibration_recovery_figure.py` (not part of this script's collection).

## 3. CLI arguments

None (standalone execution also works; missing collection sources produce a warning and are skipped).

## 4. Function specifications (the 4 generated figures)

### `make_panel_overview(panel)` — fig. 3.1
Two panels (sex=total, representative ages 40 and 75) overlaying the mortality-rate trends 1950–2024 of the 8 diseases on a log scale (zero-rate points are dropped because of the log axis). Shows the scale of the input data and the diversity of trends.

### `make_smoothing_before_after(panel, *, disease="heart_disease", sex="total", cutoff=2022)` — fig. 3.2
Applies only `fit_scale_bb()` (no projection) to the matrix up to the cutoff year and compares before/after the two-dimensional Whittaker–Henderson smoothing (eqs. 3.1–3.2). Left panel: year cross-sections (ages 40/60/75); right panel: age cross-sections (years 1970/2000/cutoff). Observed = markers, smoothed = solid lines, log scale.

### `make_blend_schematic(panel, *, disease="heart_disease", sex="total", cutoff=2022, horizon=2045)` — fig. 3.3
After fit/project, plots the final improvement rates `fit.improvement_final` (annual, in %) for ages 40/60/75 from year 2000 onward, showing how observed improvement rates blend into the long-term rate L toward the convergence year P (eq. 3.5). Adds a horizontal dashed line at L, vertical dotted lines at the cutoff year and P, and shading in between. Projects to horizon 2045 to also show the flattening after P.

### `make_backtest_design()` — fig. 4.1
A schematic using no data. For each of the three cutoff rows, draws the training window (blue, 1950–cutoff) and validation window (red, cutoff–2024, with the year count annotated) as horizontal bars, overlaying the COVID-19 period (2020–2022) as a grey band. Shows how the 3-cutoff design straddles the COVID break.

## 5. Collection

### `collect_backtest_figures()`
Copies existing figures with `shutil.copyfile` according to the module constant `COLLECT` (a dict from `output/`-relative path to paper file name). **Missing figures print a `WARN` and are skipped**, and processing continues (running `run_all.sh` end-to-end produces all of them).

## 6. Implementation notes

- The hyperparameters `SCALE_BB_CONFIG` are identical to `run_backtest.py` (so the explanatory figures match the actual validation setup).
- The default examples of figs. 3.2 and 3.3 use heart_disease / cutoff 2022; the example disease can be changed via keyword arguments.
- The destination `sections/figures/` is committed to git. The file names are referenced from the paper body, so rename them only together with the body.
