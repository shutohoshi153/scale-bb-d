[日本語](README.md) | **English**

# backtest — §3 Backtest Reproduction Package

*English translation of [README.md](README.md) (as of 2026-08-05). If the versions disagree, the Japanese version is authoritative.*

This directory is a self-contained package for **standalone reproduction and verification** of the **backtest** (point-forecast accuracy and directional accuracy) in paper §3 "Data and Methods". It regenerates everything in one shot, from the raw Vital Statistics table 5-15 through all artifacts for point-forecast accuracy (§5) and directional accuracy (§6).

It has no dependency on any other directory in the repository (input data and the algorithm core are all bundled).

For a detailed explanation of what each script does (inputs, processing, outputs), see [SCRIPTS.en.md](SCRIPTS.en.md).

> One of the two packages under `Paper_ICA2026/reproduction/`. It shares the algorithm core and input mortality data
> with its sister package `../generational/` (APC generational assumed-rate generation, Appendix B; details in `../generational/README.md`).
> For the overall division of roles and consistency, see `../README.md`.

---

## Quick Start

```bash
# Use the repository .venv (recommended; pandas/numpy/scipy/matplotlib included)
bash run_all.sh

# Specify a Python interpreter explicitly
PY=/path/to/python bash run_all.sh
```

It completes in a few minutes, and all artifacts are generated under `./output/`.

**Dependencies:** Python 3.10+ and `pandas` / `numpy` / `scipy` / `matplotlib` only.

---

## Validating on your own incidence experience (added 2026-09-30)

The paper tests the framework on cause-specific mortality because open statistics contain no long incidence panel (§7.3 of the paper). An insurer that holds incidence experience can run the same validation — fit, projection, three baselines, MAPE, directional accuracy and its ex-post majority benchmark — on its own panel with `run_own_data.py`. No data leave the machine.

```bash
python run_own_data.py --panel /path/to/panel.csv --train-cutoff 2019 --validation-end 2024 --name own_2019
```

The input CSV has the columns of `data/disease_panel_mortality.csv`:

| Column | Content |
|---|---|
| `disease_id` | any label (a disease, a benefit, a rider) |
| `sex` | `total` / `male` / `female` (absent series are skipped) |
| `year` | year of observation (gaps are allowed) |
| `age_low` | lower age of a 5-year age group; ages 20–89 are used |
| `rate_per_100k` | the rate to be projected (incidence or claim rate per 100,000 exposed) |
| `deaths` | number of events behind the rate (optional; not used by the equal-weight fit) |

Outputs go to `output/<name>/tables/` (`own_data_summary.csv` holds MAPE and DA by series). Compare `DA_scalebb` with `DA_majority_benchmark` (§3.3 of the paper) and `MAPE_scalebb` with the three baselines (§5). A cutoff on either side of a structural break is informative (§4). **Default handling of zero rates** (common in incidence data with few events): at ages whose cutoff-year rate is zero or missing the projection starts from the smoothed rate (the default of `select_base_rates`), and those ages are left out of the directional accuracy, since a direction measured from zero is not the direction of the projection (§3.3 of the paper). MAPE leaves out cells whose actual rate is zero. For series with many zeros, widen the age groups or aggregate to series with more events first.

For scenario generation and BEL valuation on your own data see "Running on your own data" in `../bel_demo/README.md`.

---

## Package Layout

```
backtest/
├── run_all.sh                       One-shot reproduction driver (full §3 pipeline)
├── _paths.py                        Self-contained path layer (see "Modifications from the Original Scripts" below)
├── build_panel.py                   [1] Table 5-15 → disease panel (§3.1)
├── run_backtest.py                  [2] ScaleBB fit/project + validation (§3.2)
├── run_baselines.py                 [3] naive/mean_3pts/loglin baselines (§3.3.1)
├── compute_directional_accuracy.py  [4] Directional accuracy DA (§3.3.2, Eqs. 3.9–3.10); includes the reference rules always_down / sign_last_change, the majority-direction share, the PT test and block-bootstrap intervals [ADD 2026-09-02]
├── compare_base_levels.py           [5b] sensitivity of Scale BB-D MAPE to the projection base level (observed / mean of last 3 observation points / smoothed) (§5.4, Table 5.5) [ADD 2026-09-03]
├── compute_weighted_mape.py         [5c] deaths-weighted and ages-40+ MAPE (§5.4, Table 5.4) [ADD 2026-09-03]
├── compute_da_inference.py          [4] two-way (age × validation year) bootstrap intervals for DA and its differences from the majority benchmark and loglin_trend (§3.3, Table 6.1) [ADD 2026-09-30]
├── compute_rolling_origin.py        [4b] Rolling-origin DA and MAPE gap for cutoffs 2014–2022 (§6.6, Fig. 6.4) [ADD 2026-09-02]
├── run_own_data.py                  runs the same validation on your own rate panel (§7.3 of the paper) [ADD 2026-09-30]
├── compare_same_anchor.py           [3] trend comparison from a common starting level (observed / 3-point mean / each method's own fitted level) (§5.3, Table 5.4) [ADD 2026-09-30]
├── compute_fixed_horizon.py         [3] fixed-horizon (h = 1, 2, 3 years ahead) rolling-origin comparison, cutoffs 2014–2023 (§5.3, Table 5.5) [ADD 2026-09-30]
├── compare_cutoffs.py               [5] Cross-comparison over 3 cutoffs (§4)
├── make_calibration_recovery_figure.py  [6] Recalibration experiment for direction-reversal diseases (§6.5, Fig. 6.3)
├── make_paper_figures.py            [7] Generation and collection of paper figures (→ ../../sections/figures/)
├── vendor/
│   └── experience_rate/_scalebb_core/
│       ├── model.py                 Scale BB core (§3.2, Eqs. 3.1–3.6). Bundled unmodified from EAS
│       └── apc_model.py             APC extension (Appendix B, Eqs. B.1–B.2). Bundled for reference. [CHG 2026-09-03] the `dummy` mode now fits the non-COVID trend within a local window (`covid_trend_window`=15 years) (Appendix B Table B.1, §10.5) [ADD 2026-09-03] `project_scale_bb_apc(apply_cohort=True)` carries γ(c) into the projection (off by default; better than AP at cutoff 2014 in the §10.5 test, worse at 2019–2022). [CHG 2026-09-03] `decompose_apc_additive` now removes the linear component of γ and smooths γ along the cohort axis (`lam_gamma`) [FIX 2026-09-30] the cohort penalty now follows the actual birth-cohort direction (`cohort_year_step`: one age-group step advances the calendar year by the group width, (i+1, j+5) for 5-year age groups on an annual grid; the earlier code used (i+1, j+1), which does not follow a birth cohort; Appendix B Eq. B.2). `model.py` is unchanged, so the numbers of §5–§6 and §8 are unaffected
├── data/
│   ├── raw/5-15_…_0003411659.csv    Input: Vital Statistics table 5-15 (1950–2024)
│   ├── disease_estat_mapping.csv    Disease → cause-of-death code mapping (§3.1.2)
│   └── prebuilt_disease_panel_mortality.csv   Expected output of build_panel (for cross-checking)
└── output/                          [Generated] Rebuilt by run_all.sh (not under git)
```

## Execution Order and Correspondence to §3

`run_all.sh` follows the reproduction procedure in the report and runs the following in order.

| Step | Script | Artifacts | Correspondence to §3 |
|---|---|---|---|
| 1 | `build_panel.py` | `data/disease_panel_mortality.csv` (8 diseases × 3 sexes × 25 years × 21 ages = 12,600 rows) | §3.1 data and disease mapping |
| 2 | `run_backtest.py` (cutoffs 2014/2021/2022) | `output[/cutoff_*]/tables/validation_summary.csv` etc. | §3.2 ScaleBB fit/project, Eqs. (3.1)–(3.6) |
| 3 | `run_baselines.py` (same 3 cutoffs) | `output[/cutoff_*]/tables/validation_summary_baseline.csv` etc. | §3.3.1 baselines, §3.3.2 MAPE/bias (Eqs. 3.7–3.8) |
| 4 | `compare_cutoffs.py` | `output/cutoff_comparison/` | §4 validation design (across the 3 cutoffs) |
| 5 | `compute_directional_accuracy.py` | `output/directional/` | §3.3.2 directional accuracy DA (Eqs. 3.9–3.10) → §6 |
| 6 | `make_calibration_recovery_figure.py` | `output/directional/tables/calibration_recovery.csv`, Fig. 6.3 (committed) | §6.5 recalibration experiment for direction-reversal diseases (liver / hypertensive; re-setting L and P × cutoff) |
| 7 | `make_paper_figures.py` | `../../sections/figures/` (committed) | Generation of the explanatory figures for §3 and §4 of the main text, and collection of the result figures referenced by §5 and §6 |

## Expected Key Figures (Ground Truth for Cross-Checking)

Whether the reproduction ran correctly can be checked against the following representative values (`sex=total`). All of them match the tables in §5 and §6 of the paper. They are for the settings of the main results: projection started from the observed rate of the cutoff year (`base_level="observed"`), `lam_row=40`, `lam_col=20`, annual calendar grid.

**Correction of 2026-09-30**: this section still carried values from the settings used before 2026-09-03 (projection started from the smoothed rate: cancer 7.17, total 7.73, DA total 84.29 and so on), which did not match the main results of the paper (referee comment A-0). The smoothed-start values are now written separately to `output/base_smoothed_cutoff_*/` and correspond to the row "own smoothed rate" of Table 5.4 of the paper.

**Scale BB-D MAPE [%]** (Table 5.2 of the paper; `output[/cutoff_*]/tables/validation_summary.csv`)

| disease | 2014 | 2021 | 2022 |
|---|---:|---:|---:|
| cancer | 10.38 | 3.96 | 2.83 |
| total | 7.52 | 5.11 | 1.40 |
| hypertensive | 39.06 | 12.20 | 11.12 |

**Directional accuracy DA [%]** (Table 6.1 of the paper; `output/directional/tables/directional_summary_total.csv`, cutoff=2014)

| disease | scalebb | naive_last | loglin_trend | majority benchmark |
|---|---:|---:|---:|---:|
| total | 81.43 | 0.00 | 94.29 | 95.71 |
| cerebrovascular | 91.79 | 0.00 | 91.04 | 91.79 |
| cancer | 69.57 | 0.00 | 93.48 | 94.93 |

The DA of `naive_last` is 0.00 in every cell because, by construction, $\Delta_{\text{pred}} \equiv 0$ and it carries no directional information (§3.3 of the paper).

**Automatic check against the tables of the paper** (added 2026-09-30)

```bash
python verify_paper_tables.py                                  # English final/sections_en_b1
python verify_paper_tables.py --sections ../../final/sections  # Japanese
```

The script reads all 442 cells of Tables 5.1–5.5 and 6.1–6.5 from the Markdown source of §5 and §6, recomputes them from the CSVs under `output/` and checks agreement to half a unit of the last printed digit (exit code 1 on any mismatch). It runs at the end of `run_all.sh`.

**Record of the run and reference tables** (added 2026-09-30)

`output/` is not under version control. At the end of `run_all.sh`, `write_manifest.py` writes `output/MANIFEST.json` (SHA-256 of the input data and of the algorithm core, the git commit of the code, the smoothing and projection settings, library versions, time of the run) and copies the 14 summary CSVs behind the tables of the paper to `reference_tables/`, which is tracked. To check the numbers without running the pipeline, read `reference_tables/`. Output directories are separate for each setting and are not overwritten: main results in `output/` and `output/cutoff_<y>/`, starting-level sensitivity in `output/base_mean_obs_cutoff_<y>/` and `output/base_smoothed_cutoff_<y>/`.

## Modifications from the Original Scripts (Stated for Transparency)

The 5 bundled scripts make **no change whatsoever to the algorithm, aggregation, or plotting logic** of the research-side `ScaleBB/BackTest_2015_2024/scripts/`. The only modifications are the **few path-anchor lines at the top of each file**:

- Originally, `ROOT = Path(__file__).resolve().parents[2]` walked up to the repository root and referenced `EAS/src`, `ScaleBB_Research/data/raw`, and `MedicalInsuranceProduct/`. These were invalidated by the 2026-07 repository reorganization.
- In this package, the input data and algorithm core are bundled, and paths are resolved in a single place, `_paths.py`. Each modified location in the scripts is marked with a `# [REPRO]` marker.

`vendor/experience_rate/_scalebb_core/` is an **unmodified copy** from EAS (`ValidationTools/EAS/src/experience_rate/_scalebb_core/`), and is the very implementation corresponding to the equations in §3.2/Appendix B.

## Data Sources and License

- **Vital Statistics table 5-15** (statistics table ID 0003411659): source **Ministry of Health, Labour and Welfare, "Vital Statistics" (人口動態調査) (portal site of official statistics of Japan, e-Stat)**. Commercial use is permitted with attribution under the Government of Japan Standard Terms of Use (Version 2.0).
- For the list of sources and terms of use of the bundled third-party data, see `../../DATA_SOURCES.md`.
- This package is an academic validation based on public data and does not guarantee the profitability or capital requirements of any specific product (see paper §10).
