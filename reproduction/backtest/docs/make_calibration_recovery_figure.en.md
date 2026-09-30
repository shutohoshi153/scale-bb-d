[日本語](make_calibration_recovery_figure.md) | **English**

# Design Document — `make_calibration_recovery_figure.py` ([6] recalibration experiment, §6.5 fig. 6.3)

*English translation of [make_calibration_recovery_figure.md](make_calibration_recovery_figure.md) (as of 2026-08-06). If the versions disagree, the Japanese version is authoritative.*

> For the cross-script overview see [../SCRIPTS.en.md](../SCRIPTS.en.md); for the package as a whole see [../README.en.md](../README.en.md).

## 1. Role and position

For the **trend-reversal diseases** (liver / hypertensive, sex = total), which miss direction almost entirely at cutoff 2014, runs a 5-setting comparison experiment on which intervention recovers directional accuracy (DA), and generates paper figure 6.3. `run_all.sh` step [5]. Corresponds to §6.5 "Handling diseases with trend reversal".

## 2. Experiment design (5 settings)

The common Scale BB hyperparameters are held fixed (`COMMON_CFG`: λ_row = λ_col = 40, 2nd-order differences, taper from age 90 — identical to `run_backtest.py`), and **only three things vary: the cutoff, the long-term improvement rate L, and the convergence year P**:

| Label | cutoff | L | P | Channel |
|---|---|---|---|---|
| `2014_default` | 2014 | +1% | 2035 | Restatement of §6.1 (reference) |
| `2014_L0` | 2014 | 0% | 2035 | Calibration channel (swap L only) |
| `2014_L0_P2020` | 2014 | 0% | 2020 | Calibration channel (plus earlier convergence) |
| `2021_default` | 2021 | +1% | 2035 | Data channel (recent reversal enters training) |
| `2022_default` | 2022 | +1% | 2035 | Data channel (one more year) |

- **Calibration channel**: recover direction by re-setting L and P per disease.
- **Data channel**: recover by letting the recent trend into the training data.

## 3. Inputs and outputs

**Input**: `data/disease_panel_mortality.csv` (falls back to the bundled `prebuilt_disease_panel_mortality.csv` if absent).

**It does not depend on any existing artifacts under `output/`** — for all 5 settings, everything from fit/project through the DA computation is re-run in-script. The DA of the default settings (`2014_default`, etc.) matches the output of `compute_directional_accuracy.py` (`directional_summary_total.csv`), which can serve as a consistency check.

**Outputs**

| File | Content |
|---|---|
| `output/directional/tables/calibration_recovery.csv` | 10 rows (2 diseases × 5 settings). Columns: `disease`, `setting`, `cutoff`, `long_term_rate`, `convergence_year`, `n_cells_evaluable`, `dir_acc_pct` |
| `output/directional/figures/calibration_recovery.png` | DA bar chart of the 5 settings |
| `../../sections/figures/fig_6_3_calibration_recovery.png` | Paper copy of the above (**committed to git**) |

## 4. CLI arguments

None. The configuration is fixed in the `SETTINGS` / `DISEASES` / `COMMON_CFG` constants at the top.

## 5. Processing flow (`main()`)

1. Creates the output directories (`output/directional/` and `../../sections/figures/`) and loads the panel.
2. Calls `directional_accuracy()` for the 10 combinations of disease × 5 settings, collecting evaluable-cell counts and DA%, and writes the CSV.
3. Draws the bar chart: the 2 diseases on the x-axis, 5 bars per disease. **Color = cutoff** (same palette as `scalebb_directional_per_cutoff.png`: 2014 red / 2021 orange / 2022 green); **hatching + transparency = the recalibrated settings at cutoff 2014** (`//` = L0, `xx` = L0+P2020). Annotates the DA value above each bar and draws the 50% reference line.
4. Saves the figure under `output/` and copies it via `shutil.copyfile` to `sections/figures/fig_6_3_calibration_recovery.png`.

## 6. Function specifications

### `directional_accuracy(panel, disease, cutoff, L, P) -> (n_eval, da_pct)`
The core: fit/project under the given setting and return the DA.

1. Builds the training matrix (years ≤ cutoff, ages 20–89) via `build_matrix()`.
2. Runs `fit_scale_bb()` → `project_scale_bb(base_year=cutoff)` with `ScaleBBConfig(last_observed_year=cutoff, horizon_year=2024, long_term_rate=L, convergence_year=P, **COMMON_CFG)`.
3. Takes the validation-year actuals (cutoff+1 … 2024) and the cutoff-year observed rates directly from the panel, and per cell compares `sign(actual − rate_at_cutoff)` with `sign(predicted − rate_at_cutoff)`. **The definition is identical to `compute_directional_accuracy.py`** (cells with zero actual change are excluded; missing cells are skipped).
4. Returns `(evaluable cells, DA% rounded to 2 decimals)`.

## 7. Implementation notes

- The validation window differs across settings (cutoff 2014 → 10 years / 2021 → 3 years / 2022 → 2 years), so `n_cells_evaluable` differs too. The DA comparison is a comparison of recovery under the same disease and same definition, not a test with equalized cell counts.
- Figure 6.3 is not in the `COLLECT` set of `make_paper_figures.py`; it is the only figure **written directly to `sections/figures/` by this script**.
- Keeping all hyperparameters other than L and P identical to `run_backtest.py` is the control condition of the experiment; change both together.
