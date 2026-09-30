[日本語](age20_pipeline_migration_20260423.md) | **English**

# Full Migration of the Analysis Pipeline to an Age-20 Start (2026-04-23)

*English translation of [age20_pipeline_migration_20260423.md](age20_pipeline_migration_20260423.md) (as of 2026-08-05). If the versions disagree, the Japanese version is authoritative.*

## 1. Background and Purpose

Anticipating application to medical insurance products for younger policyholders
(educational endowment insurance, juvenile whole-life medical insurance, and
juvenile cancer insurance), we rebuilt the experience-rate / expected disease
incidence rate pipeline — which previously defaulted to a **start age of 40** —
so that **every layer starts at age 20**.

This document records the **changes and verification results across all layers**:
the parquet panels generated from `EAS/data/RowData/`, the EAS CLI / Web UI /
REST API, and the research backtest / visualization scripts.

## 2. Preliminary Investigation: The Raw-Data Layer Already Supports Age 20

### 2.1 Age classes in `mortality_apc_panel.parquet`

```
全 age_code (22 階級):
  a00_04, a05_09, a10_14, a15_19,
  a20_24, a25_29, a30_34, a35_39,
  a40_44, a45_49, a50_54, a55_59,
  a60_64, a65_69, a70_74, a75_79,
  a80_84, a85_89, a90_94, a95_99, a100p, total
```

(The header line reads "all age_code values (22 classes)".)

**Conclusion**: mortality_apc_panel covers the **full period 1950–2024 × 20 age
classes × 3 diseases × 3 sexes** with no missing values. **The scripts from raw
data through panel construction contain no age filter** (i.e., they already
support age 20).

### 2.2 Scripts involved (no changes required)

| Script | Input | Output | Age filter |
|---|---|---|---|
| `scripts/build_disease_panel.py` | e-Stat 5-15, Z3-2, Z4-4, Z5-2, Z68 | `mortality_apc_panel.parquet` and others | **None** (all ages retained) |
| `EAS/scripts/build_mortality_incidence_panel.py` | `mortality_apc_panel.parquet` | `incidence_panel` (mortality) | **None** |
| `EAS/scripts/build_incidence_panel.py` | Panels for each rate_type | `incidence_panel.csv` | **None** |
| `EAS/src/experience_rate/etl.py` | `incidence_panel.csv` | `population_incidence` table | **None** |

→ **No changes needed from raw data → panel → DB.** The problem was that
**age_min=40 was hard-coded as the default** in the downstream analysis
scripts, CLI, and Web UI.

## 3. Changes Made — Complete File List

### 3.1 EAS core (production)

| File | Location changed | Change |
|---|---|---|
| `EAS/config.yaml` | `scalebb_presets.defaults.age_min` | 40 → **20** |
| `EAS/config.yaml` | `scalebb_presets.defaults.lam_col` | 40.0 → **60.0** (suppresses young-age noise) |
| `EAS/config.yaml` | `scalebb_presets.generational.issue_age` | 40 → **20** |
| `EAS/config.yaml` | `scalebb_presets.generational.age_min` | 40 → **20** |
| `EAS/src/experience_rate/cli.py` | `scalebb-fit --age-min default` | 40 → **20** |
| `EAS/src/experience_rate/cli.py` | `scalebb-heatmap --age-min default` | 40 → **20** |
| `EAS/src/experience_rate/cli.py` | `_merge_preset_apc` fallback | 40 → **20** |
| `EAS/src/experience_rate/scalebb.py` | `run_fit()` / `run_heatmap()` argument defaults | 40 → **20** (×2) |
| `EAS/src/experience_rate/scalebb_apc.py` | `run_apc_fit()` argument default | 40 → **20** |
| `EAS/src/experience_rate/web/app.py` | `ScaleBBFitRequest.age_min` | 40 → **20** |
| `EAS/src/experience_rate/web/app.py` | `ScaleBBFitRequest.lam_col` | 40.0 → **60.0** |
| `EAS/src/experience_rate/web/app.py` | `ScaleBBHeatmapRequest.age_min` | 40 → **20** |
| `EAS/src/experience_rate/web/static/index.html` | `#sb-fit-age-min` value attribute | 40 → **20** |
| `EAS/docs/Scale_BB機能.md` | age_min defaults table / sample code | 40 → **20** (5 places) |
| `EAS/README.md` | Sample code | 40 → **20** (2 places) |

### 3.2 Research scripts (`scripts/`)

| File | Location changed | Change |
|---|---|---|
| `scripts/scale_bb_disease.py` | `load_mortality_matrix()` default | 40 → **20** |
| `scripts/scale_bb_disease.py` | `fit` / `run-all` argparse defaults | 40 → **20** (×2) |
| `scripts/backtest_ap_vs_apc.py` | `load_matrix()` default / argparse | 40 → **20** (×2) |
| `scripts/backtest_scalebb_vs_traditional.py` | `load_matrix()` default / argparse | 40 → **20** (×2) |
| `scripts/visualize_scale_bb_heatmaps.py` | argparse default | 40 → **20** |
| `scripts/build_traditional_predicted_rates.py` | `AGE_MIN` constant | 40 → **20** |
| `scripts/build_traditional_predicted_rates.py` | `AGE_CODE_TO_LOW` | **a20_24 – a35_39 added** |

### 3.3 Files that required no changes

- `scripts/scale_bb_model.py` — pure numerical routines; has no age_min parameter
- `scripts/scale_bb_apc_model.py` — same as above
- `scripts/build_generational_rate_table.py` — already `default=0` (controlled by the caller)
- `scripts/build_disease_panel.py` — raw-data panel construction, no age filter

## 4. Verification: Does the Age-20 Start Take Effect Without `--use-preset`?

### 4.1 Smoke test

```powershell
$env:PYTHONPATH="src"; $env:PYTHONIOENCODING="utf-8"
# Do not specify age-min explicitly (confirm the new default=20 takes effect)
python -m experience_rate scalebb-fit `
    --source mortality --disease cancer --sex male --year-min 1990 `
    --output ../data/processed/_smoketest_fit_age20.parquet
```

**Expected result**: `n_age=14` (14 classes, 20-24 through 85-89), and
`--age-min 20 --age-max 89` is passed to the subprocess.

**Actual result** (2026-04-23):

```
[fit] disease=cancer sex=male n_age=14 n_year=17 year_range=1990-2024
[saved] scalebb_improvement 238 rows (run_id=20260423T092649)
[scalebb] $ python scripts/scale_bb_disease.py fit --sex male `
         --age-min 20 --age-max 89 --output ...
```

**Verdict**: **Pass.** Runs with an age-20 start (`n_age=14`) without any
explicit specification.

### 4.2 Web UI default value

- Check the Age Min input field on the Scale BB tab at `http://localhost:8000`
- The `value="20"` in `index.html#sb-fit-age-min` is reflected

## 5. Operational Impact

### 5.1 Compatibility with past run_ids

| Item | Impact |
|---|---|
| Existing `scalebb_run` / `scalebb_improvement` / `scalebb_projection` tables | **No change.** Each row is keyed by `run_id`, so data from the age_min=40 era is retained |
| Existing parquet outputs (`scalebb_fit.parquet`, etc.) | **No change.** New outputs have 14 classes (20-85); old outputs have 10 classes (40-85) |
| Existing `predicted_rate_generational` entries | Because `year_lookup` changes to an `issue_age=20` basis, **old and new results are managed under separate run_ids** |

### 5.2 Ensuring backward compatibility

Explicitly specifying `--age-min 40` reproduces the previous results:

```powershell
python -m experience_rate scalebb-fit --age-min 40 ...
```

### 5.3 Impact on numerical results

Note that even for the same `issue_year`, changing `issue_age=40→20` changes
`year_lookup`, so **the values differ even in output files with the same name**.

| `issue_age` | `year_lookup` at age=40 (issue_year=2026) | Female cancer value at age 40 |
|---:|---|---:|
| 40 (old) | 2026 | 33.3 / 100k |
| **20 (new)** | **2046** (20 years later for entry at age 20) | **21.6** / 100k |

This is due to the 20-year accumulation of the long-term improvement rate
L=1%/year (×0.82) plus the APC re-smoothing effect.

## 6. Full Pipeline Diagram (After Age-20 Migration)

```
[RAW DATA]                                   [includes data from age 20 onward]
  EAS/data/RowData/
    ├ estat_processed/vital_statistics/5-15_…csv   (cause of death × 5-yr age × year)
    ├ estat_processed/patient_survey/Z*.csv
    ├ estat_processed/population/pop_5yr_age_…csv
    └ cancer_incidenceNCR(2016-2023).xls
         ↓
[PANEL BUILD]                                [no age filter = all ages retained]
  scripts/build_disease_panel.py
    → data/processed/mortality_apc_panel.parquet
    → data/processed/age_period_panel.parquet
    → data/processed/disease_period_panel.parquet
         ↓
[EAS INCIDENCE LOAD]                         [no age filter]
  EAS/scripts/build_incidence_panel.py
  python -m experience_rate load-incidence
    → population_incidence table
         ↓
[ScaleBB ANALYSIS]                           [new default: age_min=20]
  python -m experience_rate scalebb-apc-fit --use-preset
    → scalebb_improvement (n_age=14)
    → scalebb_cohort_effect (n_cohort=90+)
  python -m experience_rate scalebb-apc-project --use-preset
    → scalebb_projection (rate_projected)
         ↓
[EXPECTED INCIDENCE RATE TABLES]             [ages 20-85, 66 single ages]
  python -m experience_rate scalebb-gen-table --use-preset
    → predicted_rate_generational (issue_age=20)
    → CSV: rate_by_age_M_YYYY_disease_sex.csv

[TRADITIONAL METHOD COMPARISON]              [new default: AGE_MIN=20]
  python scripts/build_traditional_predicted_rates.py
    → predicted_rate_master_traditional.csv (1,188 rows)
```

## 7. Remaining Issues

1. **Small-sample stability at ages 20-29**: Mortality rates for heart disease
   and cerebrovascular disease are extremely small in absolute terms
   (0.3-5 / 100k). Because year-to-year fluctuations have a large impact, we
   raised `lam_col=60`, but long-term validation continues
2. **Ongoing updates of young-cohort γ(c)**: For cohorts born in 2004 or later
   (age 20 at the observation endpoint of 2024), γ is based on only one year of
   data. Refitting after incorporating 2025-2029 data will stabilize it
3. **Extension to other pipelines (`rate_type=registry/initial_visit/discharge`)**:
   Currently only mortality supports age_min=20. Extending the other three
   streams (cancer registry covers only the short period 2016-2023; Patient
   Survey Z4-4 covers 9 time points over 1999-2023) will be considered
   separately

## 8. Related Documents

- [`apc_predicted_rate_tables_by_sex_20260423.md`](./apc_predicted_rate_tables_by_sex_20260423.md)
  — APC sex-specific assumed rate tables + Appendix B (age-20-start version)
- [`traditional_predicted_rate_tables_by_sex_20260423.md`](./traditional_predicted_rate_tables_by_sex_20260423.md)
  — Traditional-method tables + Appendix A (age-20-start version)
- [`methodology_apc_extension_20260422.md`](./methodology_apc_extension_20260422.md)
  — Methodology of the ScaleBB APC extension
- [`validation_scalebb_vs_traditional_20260422.md`](./validation_scalebb_vs_traditional_20260422.md)
  — Backtest of the AP model vs. the traditional method
