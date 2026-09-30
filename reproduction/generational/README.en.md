[日本語](README.md) | **English**

# generational — Expected Incidence Rate Table Generation Scripts and Traceable Verification Environment

*English translation of [README.md](README.md) (as of 2026-08-05). If the versions disagree, the Japanese version is authoritative.*

> This package is part of `Paper_ICA2026/reproduction/` (migrated on 2026-07-22 from the former
> `CoAuthor_Share_20260711/05_reproduction/`). It corresponds to the reproduction of paper **§3.3 (APC extension)**
> and to its forward-looking runtime, the generational projection (generation of per-issue-year assumed-rate tables;
> not treated as a chapter of the main text and explained in this README instead).
> It shares the algorithm core with its sister package `../backtest/` (point-forecast accuracy and directional accuracy, §3.4/§5/§6),
> and together the two reproduce all of §3. For the overall division of roles, see `../README.md`.

This is the full pipeline for generating **expected disease incidence rate tables** with ScaleBB (APC extension),
bundled so that co-authors can re-run and trace-verify it on their own machines.
On 2026-07-15, a full reproduction run was performed on a copy of this directory,
and the outputs were confirmed to match the reference outputs (see §5).


> [Note 2026-09-03] The projection base of the algorithm core `EAS/src/experience_rate/_scalebb_core/model.py` was changed from the smoothed rate of the base year to the observed rate (`ScaleBBConfig.base_level="observed"`, as equation 3.6 of the paper states). The `reference_output/` and `reference_output_20260902/` of this package were generated with the former base (smoothed rate); re-running with the current code changes the level of the generated rate tables (the improvement-rate paths are unchanged). The re-run was done on 2026-09-03 and the corrected outputs are in `reference_output_20260903/` (§5; the APC tables are numerically unchanged, the AP tables move by +1.1% on average). Outputs reproduced with the current code should be compared against `reference_output_20260903/`.

## 1. Important Note on Data Provenance (to Prevent Misunderstanding)

- **The input data for the assumed incidence rate tables is disease-specific mortality from the e-Stat Vital Statistics (人口動態統計)**
  (`EAS/data/processed/mortality_apc_panel.parquet`; mortality rates are used as a proxy for incidence rates).
- **The data originating from the National Cancer Center = National Cancer Registry (NCR) incidence rates**
  (`EAS/data/RowData/cancer_incidenceNCR(2016-2023).xls`; source: National Cancer Center
  Cancer Information Service, "Cancer Statistics" (National Cancer Registry)) are
  **not** an input to the assumed-rate tables; they are used as the **highest-quality (A-tier) benchmark** of true incidence
  (`EAS/scripts/build_cancer_registry_panel.py` converts them into an incidence panel → stored in `population_incidence`
  with `rate_type='registry'`). The bundled `.xls` is the original file downloaded from the provider, unmodified;
  the post-panelization figures are derived products of this research (the provider bears no responsibility for the processed results).
- Quantification of the divergence between the mortality-based assumed rates and the cancer-registry incidence rates is
  recorded as **future work** in specification `docs/apc_predicted_rate_tables_by_sex_20260423.md` §B.9.
- **On terminology (supplementary note accompanying the 2026-07-15 retitling):** the "assumed incidence rate tables" produced by
  this pipeline are, in substance, rate tables computed from **cause-of-death mortality rates** (per 100,000 population). In the
  paper's (post-retitling) framework, these cause-of-death mortality rates are used in two layers: **(i) as a proxy for medical-insurance
  disease incidence rates**, and **(ii) as the direct target itself (the direct assumption) for critical-illness death benefits**.
  The "incidence" wording in file names and legacy labels is product-side naming; please note that the inputs and computations
  are consistently cause-of-death mortality rates
  (since the algorithm is agnostic to the meaning of its input, the reproduction results and figures are unchanged).

## 2. Layout

| Path | Contents |
| --- | --- |
| `EAS/` | Runtime environment (a copy of the self-contained SQLite + Python application). Includes scripts, algorithm core, configuration, and input data |
| `EAS/scripts/build_cancer_registry_panel.py` | **Cancer registry (NCR) → incidence panel** conversion script |
| `EAS/data/lifetable/seimeihyo960718.xlsx` | Standard life tables (source: the 7 series of "Standard Life Tables 1996 / 2007 / 2018" published by The Institute of Actuaries of Japan (公益社団法人日本アクチュアリー会), bundled into a single workbook). Used for validity checks of the input data (§4.3) |
| `EAS/src/experience_rate/_scalebb_core/` | ScaleBB / APC algorithm core (2D Whittaker-Henderson, cohort penalty, generational projection) |
| `EAS/config.yaml` | Parameter presets (currently in the **age-20-start (age20)** configuration state) |
| `docs/apc_predicted_rate_tables_by_sex_20260423.md` | **Specification and process document**: purpose, inputs, full pipeline diagram, all reproduction commands, result summary |
| `docs/age20_pipeline_migration_20260423.md` | Background and configuration changes for the age-20-start extension |
| `reference_output/` | **Reference outputs for trace verification** (a snapshot of the current artifacts generated on the research side) |
| `reference_output/predicted_rate_apc/` | APC assumed-rate tables (issue_age=40, issue years 2024–2028) |
| `reference_output/predicted_rate_apc_age20/` | APC assumed-rate tables (issue_age=20) |
| `reference_output/predicted_rate_tables/` | Legacy AP version (for comparison) |
| `reference_output/scalebb_apc_*.parquet etc.` | Intermediate artifacts of fit / projection |

Repository originals: `EAS` is from `ICA/ValidationTools/EAS/`, and the specification documents are from `ICA/ScaleBB/Research/docs/`.
To reduce size, the raw e-Stat data (`estat_api/`, `estat_processed/`, ~235MB) is not bundled
(the pre-built panels are bundled in `EAS/data/processed/`).

> **On the exclusion of the experience-rate (A/E) analysis features**
> This research uses no actual in-force, movement, or claims data whatsoever,
> and does not use experience-rate (A/E) analysis. Therefore the following features of the
> original `EAS` are **excluded from this distribution**. What is bundled is only the path
> that takes population statistics (e-Stat / National Cancer Registry) as input.
>
> - Individual medical insurance importers (the `ins_*` tables, `import-validate` / `import-table` /
>   `import-all` / `import-history`, YAML mapping definitions)
> - Experience-rate and benchmark analysis (`analyze` / `analyze-benchmark`)
> - Web UI / REST API (`serve`, the FastAPI stack)
> - Sample policy data generation (`generate_medical_sample.py` / `generate_lapse_sample.py`)
>
> To consult these features in the original, see `ICA/ValidationTools/EAS/`.

## 3. Setup

Python 3.11+ is assumed. Everything is run directly under the `EAS/` directory.

```bash
cd Paper_ICA2026/reproduction/generational/EAS
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=src

python -m experience_rate init --drop   # Initialize the SQLite schema
```

> The command examples in the specification document use PowerShell notation (`` ` `` line continuation, `$env:PYTHONPATH`)
> and the old directory layout (`../data/processed/...`). In this environment, read them as bash +
> EAS-relative paths (`data/processed/...`) — the steps below are already converted.

## 4. Reproduction Procedure

### 4.1 Expected Incidence Rate Tables (APC Version, Both Sexes × 3 Diseases)

```bash
# (1) APC fit (2D WH smoothing + cohort penalty + COVID dummies)
python -m experience_rate scalebb-apc-fit --source mortality --sex male \
  --disease cancer heart_disease cerebrovascular --use-preset --run-id male_repro

# (2) projection (improvement rate × long-term rate L blend, up to 2100)
python -m experience_rate scalebb-apc-project \
  --fit data/processed/scalebb_apc_fit_male.parquet --use-preset --run-id male_repro_proj

# (3) generational projection tables (per-issue-year 1D [age], log-linear single-age interpolation)
python -m experience_rate scalebb-gen-table --run-id male_repro_proj --use-preset \
  --output-dir data/processed/predicted_rate_repro

# For female, run the same with --sex female / the female fit file name
```

**Note**: the bundled `config.yaml` is in the **age20 preset** state (`age_min=20, issue_age=20, lam_col=60`).
Outputs under this configuration correspond to `reference_output/predicted_rate_apc_age20/`.
To reproduce the issue_age=40 version (`reference_output/predicted_rate_apc/`), either restore `config.yaml`
to the age-40-start parameters of specification §4.1 (`age_min=40, lam_col=40, issue_age=40`),
or specify them explicitly via CLI arguments.

**Updated 2026-09-02 (smoothing-grid correction and re-examination of `lam_col`)**: `expand_to_annual_grid`
was added to the algorithm core (`EAS/src/experience_rate/_scalebb_core/model.py` / `apc_model.py`) so that
smoothing is performed on a contiguous calendar-year grid (missing years with weight 0; `ScaleBBConfig.annual_grid=True`
by default). Previously the observation columns 1950, 1955, …, 2010, 2013, … were treated as equally spaced, which
inflated the improvement rates at the switch from 5-year to yearly data (see paper §3.2.1). `lam_col=60` was
re-examined after this correction: sweeping `lam_col ∈ {10, 20, 30, 40, 60, 80}` on the APC fit for 2 sexes × 3
diseases and measuring the criterion that motivated the age20 migration (roughness across ages and year-to-year
swing of the improvement rate at ages 20–35), 60 on the calendar grid gives the same roughness as 60 on the old grid
(mean second difference 0.16% vs 0.16%) with a smaller swing (std over the last 10 years 2.6% vs 3.1%), so **60 was
retained**. Note that the improvement rate at the 2024 endpoint depends monotonically on `lam_col` (mean over the 6
series: 0.36% at λ=20, 0.71% at 40, 0.93% at 60), so keep this sensitivity in mind if the value is changed for a
different use.

### 4.2 Building the Cancer Registry (National Cancer Center NCR) Panel

```bash
python scripts/build_cancer_registry_panel.py                    # Standalone run (prints row counts and breakdown)
python scripts/build_cancer_registry_panel.py --output data/processed/registry_panel.csv
python -m experience_rate load-incidence                          # Load the bundled incidence_panel into the DB
python -m experience_rate export-incidence --rate-type registry \
  --output output/registry_rates.csv                             # Export incidence rates to CSV with filters
```

Incidence rates derived from the cancer registry (NCR) are stored in `population_incidence` with `rate_type='registry'`,
`quality_flag='A'` (as stated in §1, they are not an input to the assumed-rate tables but the highest-quality benchmark
of true incidence). Since this reproduction environment contains no policy data,
no A/E comparison against experience rates is performed (see the note in §2).

> **Note on the panel rebuild scripts**: `scripts/build_incidence_panel.py` /
> `build_los_panel.py` / `build_discharge_panel.py` / `build_initial_visit_panel.py` take as input the raw e-Stat data
> (`data/RowData/estat_processed/`, **not bundled** for size reasons as stated in §2).
> If run without it, the corresponding sub-builders return 0 rows, so to avoid overwriting the bundled panels
> with degenerate versions, `build_incidence_panel.py` and `build_los_panel.py` abort the write
> (use `--force` only if you intend to overwrite). The bundled panels can be used as-is,
> so the normal reproduction procedure does not require re-running these.

### 4.3 Consistency Check Against the Standard Life Tables (Validity Check of the Input Data)

```bash
python scripts/analyze_standard_life_table.py
```

This cross-checks the standard life tables published by The Institute of Actuaries of Japan
(`data/lifetable/seimeihyo960718.xlsx`; the 7 series of the Standard Life Tables for life insurance 1996 / 2007 / 2018
and the Standard Life Tables for the third sector 2007 / 2018; the unprocessed source data are the Institute's published
"Standard Life Table 1996", "Standard Life Table 2007", and "Standard Life Table 2018")
against the cause-of-death mortality rates from the e-Stat Vital Statistics that serve as this pipeline's input
(`population_incidence`, `rate_type='mortality'`), and computes `ratio = population_rate / standard_rate`.
The actuarial expectation is `ratio < 1` for the death-benefit tables (due to safety loading) and `ratio > 1`
for the post-commencement annuity tables; agreement with the expected sign is shown as `[OK]`
in `[5] 妥当性チェック` (validity check) (the third-sector tables are `[REF]` = reference values, being incidence-rate concepts).

This is a validity check of the input data that is **independent of the generation path of the assumed incidence rate tables**;
the reproduction results of §4.1 are unchanged whether or not this script is run.
Outputs are saved to `output/standard_vs_population_{band10,detail}.csv`,
`standard_vs_population_judgement.csv`, `standard_life_table_tidy.csv`, and
`disease_breakdown_std2018_male_40_59.csv`.
Note that because it references `population_incidence`, run `load-incidence` of §4.2 first.

## 5. Trace Verification Method (Already Performed)

Compare the reproduction outputs against `reference_output/`.

```bash
diff data/processed/predicted_rate_repro/predicted_rate_cancer_male_issue2026_ia20.csv \
     ../reference_output/predicted_rate_apc_age20/predicted_rate_cancer_male_issue2026_ia20.csv
```

**Verification result of 2026-07-15**: in this copied environment, `init → scalebb-apc-fit (cancer, male) →
scalebb-apc-project → scalebb-gen-table` was executed and `predicted_rate_cancer_male_issue2026_ia20.csv`
was compared against the reference output. **All 46 rows matched to about 15 significant digits**
(relative difference ~1e-15; differences only in the last digit, attributable to floating-point operation ordering).
The artifacts of this verification run
(`EAS/experience_rate.db`, `EAS/data/processed/scalebb_apc_fit_male.*` /
`scalebb_apc_projection_male.*`, `EAS/data/processed/predicted_rate_verify/`) have been
left in place as-is. To re-run from scratch, rebuild the DB with `init --drop`.

**Re-run of 2026-09-02 (after the grid correction)**: fit → project → gen-table were re-run from `init --drop` for 2 sexes × 3 diseases with the corrected core. **`reference_output/`, which the co-authors refer to, was left unchanged (state as of 2026-08)**; the corrected outputs were placed in the new directory `reference_output_20260902/` (`predicted_rate_apc_age20/` 30 files, `predicted_rate_apc/` 30 files + 2 masters, `predicted_rate_tables/` 30 male/female files + 15 total files + 3 masters, `scalebb_apc_{fit,projection}_{male,female}.*`). Intermediate artifacts of the re-run (female fit/projection, age-40 fit/projection, AP `scalebb_fit.*` / `scalebb_projection.*`, `predicted_rate_*_repro*/`) were gathered under `EAS/data/processed/_rerun_20260902/`, and `EAS/data/processed/` itself and `EAS/experience_rate.db` were returned to the state of the 2026-07-15 verification run. Change from the pre-correction files: age20 APC at most ±2.8% (mostly ±1–2%; e.g. +1.4% cancer male, −1.5% cerebrovascular female), age40 APC −3.3 to +0.7%, AP (male/female) −5.0 to +1.9% — small because the 2024 endpoint has many yearly points. The age-40 version used the procedure of specification §4.2–4.3 with CLI overrides `--age-min 40 --lam-col 40` (apc-fit) and `--issue-age 40 --age-min 40` (gen-table); the AP version used §4.4 for male, female and also sex=total (the 12 sex=total files remaining in `reference_output/predicted_rate_tables/` are leftovers of a non-interpolated run of 2026-04-22; the corrected directory holds 15 interpolated files for issue years 2024–2028). Outputs reproduced with the current code should be compared against `reference_output_20260902/`.

**Re-run of 2026-09-03 (after the projection-base correction)**: fit → project → gen-table were re-run with the same procedure as on 2026-09-02 (`init --drop` → age20 APC male/female → age40 APC male/female (`--age-min 40 --lam-col 40` / `--issue-age 40 --age-min 40`) → AP male/female/total (specification §4.4, `--issue-age 40 --age-min 40`)), reflecting the change of the projection base in the core (`ScaleBBConfig.base_level="observed"`) and the `apc_model.py` fixes (local trend window `covid_trend_window`=15 for the `dummy` mode, removal of the linear component of γ(c) and cohort-axis smoothing `lam_gamma`=25, the `apply_cohort` option). The outputs were placed in the new directory `reference_output_20260903/` (same layout as `reference_output_20260902/`: `predicted_rate_apc_age20/` 30, `predicted_rate_apc/` 30 + 2 masters, `predicted_rate_tables/` 45 + 3 masters, `scalebb_apc_{fit,projection}_{male,female}.*`). Intermediate artifacts are under `EAS/data/processed/_rerun_20260903/`; `EAS/data/processed/` itself and `EAS/experience_rate.db` were returned to their prior state (`reference_output/` and `reference_output_20260902/` were not touched). Difference from `reference_output_20260902/`: **the APC tables (age20 and age40) are numerically identical in all 60 files** (relative difference 0), for two reasons: (i) the APC projection wrapper of the experience-rate aggregation process, `src/experience_rate/scalebb_apc.py`, projects with its own code rather than the core's `project_scale_bb_apc` and still starts from the smoothed rate of the base year, so the base-level change does not reach it; (ii) the `dummy`-mode fix changes only the smoothed rates of 2020–2022 (the fit's `rate_smoothed` moves by up to 6.0%), so the improvement path from the 2024 base is unchanged, and γ(c), which changed by up to 0.165, is not used in the projection. **The AP tables (`predicted_rate_tables/`) change because their base is now the observed rate**: −0.5 to +3.9% on average in the issue-year-2026 files (cancer male +3.9%, cancer total +2.5%, heart_disease male −0.5%), with a maximum single-age cell of 36.5% (cerebrovascular female, at young ages where observed and smoothed rates differ most). The mismatch between the APC wrapper's base and the paper's §3.2.2 (observed rate) remains an open item outside the scope of this re-run.

**Re-run of 2026-09-30 (after the correction of the cohort-penalty grid)**: the cohort penalty of `apc_model.py` did not follow a birth cohort (on the grid of 5-year age groups and single calendar years it linked (i+1, j+1), i.e. (x+5, y+1) in real age and year). It now runs along (i+1, j+5) (`cohort_year_step`; Appendix B Eq. B.2 of the paper). In a working copy outside the package we re-ran `init --drop` → age20 APC male/female → age40 APC male/female (`--age-min 40 --lam-col 40` / `--issue-age 40 --age-min 40`) and stored the outputs in the new `reference_output_20260930/` (`predicted_rate_apc_age20/` 30 + 2 masters, `predicted_rate_apc/` 30 + 2 masters, and the age20 `scalebb_apc_{fit,projection}_{male,female}.*`). The AP tables (`predicted_rate_tables/`) were not re-run because `model.py` is unchanged; those of `reference_output_20260903/` remain valid. `EAS/data/processed/` and `EAS/experience_rate.db` were not touched. The differences from `reference_output_20260903/` are large: for the issue-year-2026 files the mean change is −15.9 to −3.7% for age20 (cancer female −15.9%, heart_disease female −13.5%, heart_disease male −13.2%, cerebrovascular male −11.4%, cerebrovascular female −5.4%, cancer male −3.7%) and −16.4 to +4.6% for age40 (cancer male −16.4%, cancer female −9.2%, cerebrovascular female +4.6%), because the corrected penalty direction changes the end-of-data improvement rates of the smoothed surface. Compare APC outputs reproduced with the current code against `reference_output_20260930/`.

Other verification means:

- `python -m experience_rate scalebb-runs --last 10` — audit of the run history and parameters (config_json)
- Intermediate fit / projection values can be compared against `reference_output/scalebb_apc_*.parquet`
- Expected DB schema and record counts are given in specification §6.1 / §B.4

## 6. Where to Find the Scripts' Specifications and Purposes

| What you want to know | Where to look |
| --- | --- |
| Pipeline purpose, inputs, overall diagram, parameters, results | `docs/apc_predicted_rate_tables_by_sex_20260423.md` |
| Motivation and configuration diff of the age-20-start extension | `docs/age20_pipeline_migration_20260423.md` |
| Mathematical formulation (APC, identifiability) | `../../../ScaleBB/Research/docs/methodology_apc_extension_20260422.md` (corresponds to paper §3.3) |
| CLI in general, DB schema | `EAS/README.md`, `EAS/docs/Scale_BB機能.md` |
| I/O specification of the NCR panelization | Docstring at the top of `EAS/scripts/build_cancer_registry_panel.py` |
