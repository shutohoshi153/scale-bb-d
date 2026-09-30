[日本語](Scale_BB機能.md) | **English**

# Scale BB Extended Model Feature Guide (EAS-Integrated Edition)

*English translation of [Scale_BB機能.md](Scale_BB機能.md) (as of 2026-08-05). If the versions disagree, the Japanese version is authoritative.*

This document describes the usage, data flow, and operating procedures of the
**Scale BB extended model** integrated into EAS
(2D Whittaker-Henderson smoothing + future projection via a long-term-rate blend).

The original implementation (research-side core) is:

- `scripts/scale_bb_model.py`  … core algorithm
- `scripts/scale_bb_disease.py` … fit / project CLI (supports disease incidence and mortality rates)
- `scripts/visualize_scale_bb_heatmaps.py` … heatmap / trajectory generation

The EAS wrapper lives in `EAS/src/experience_rate/scalebb.py` and handles, in one pass:
subprocess execution → reading the resulting CSV/Parquet → loading into SQLite.

---

## 1. Architecture Overview

```
┌─────────────── EAS (SQLite + CLI) ─────────────┐
│  CLI: python -m experience_rate scalebb-*     │
│  DB: scalebb_run / scalebb_improvement /      │
│      scalebb_projection                        │
└────────────────────┬───────────────────────────┘
                     │ subprocess + parquet/CSV I/O
                     ▼
┌────────── Research scripts (repo root) ────────┐
│  scripts/scale_bb_model.py  (core algorithm)   │
│  scripts/scale_bb_disease.py (fit / project)   │
│  scripts/visualize_scale_bb_heatmaps.py        │
└────────────────────┬───────────────────────────┘
                     │
                     ▼
  age×period panels (CSV) under data/processed/
  ├─ mortality_apc_panel.csv      (mortality rates)
  └─ age_period_panel.csv         (consultation rates, Patient Survey)
```

**Design principles**

- The core algorithms are consolidated under `scripts/` so they can also be reused on the research side.
- EAS functions purely as a wrapper for "execute, persist, and query".
- Run results are always stored in SQLite (`scalebb_run`/`scalebb_improvement`/`scalebb_projection`)
  to enable comparison against past runs, regression analysis, and an audit trail.

---

## 2. DB Schema

### 2.1 scalebb_run

History table with one row appended per run. The full `ScaleBBConfig` is
serialized into `config_json`.

| Column | Type | Description |
|---|---|---|
| run_id | TEXT PK | `sb_fit_` / `sb_proj_` + UUID |
| kind | TEXT | `fit` / `projection` |
| source_panel | TEXT | `mortality_apc` / `age_period` |
| diseases | TEXT | comma-separated list of target disease_id values |
| sex | TEXT | `total` / `male` / `female` |
| section | TEXT | `total` / `inpatient` / `outpatient` |
| age_min, age_max | INTEGER | age range analyzed |
| year_min, year_max | INTEGER | observation-year range |
| long_term_rate | REAL | long-term rate L (projection only) |
| convergence_year | INTEGER | convergence year P (projection only) |
| horizon_year | INTEGER | final projection year |
| lam_row, lam_col | REAL | Whittaker-Henderson smoothing coefficients |
| config_json | TEXT | JSON of ScaleBBConfig |
| source_file | TEXT | Parquet/CSV file loaded from |
| created_at | TEXT | `datetime('now')` |

### 2.2 scalebb_improvement (Phase 1 results)

```
PRIMARY KEY (run_id, disease_id, sex, section, age, year)
```

- `rate_observed` : input rate (per 100,000)
- `rate_smoothed` : rate after 2D Whittaker-Henderson smoothing
- `improvement_observed` : annual improvement rate based on observed rates
- `improvement_smoothed` : annual improvement rate based on smoothed rates

### 2.3 scalebb_projection (Phase 2 results)

```
PRIMARY KEY (run_id, disease_id, sex, section, age, year)
```

- `is_observed` : 1 = observed year, 0 = future projected year
- `improvement_final` : improvement rate linearly converged to the long-term rate L via the h(y) formula in the original report
- `rate_projected` : projected rate generated cumulatively from base_year using `improvement_final`

Indexes:
- `idx_scalebb_improvement_disease_year`
- `idx_scalebb_projection_disease_year`
- `idx_scalebb_projection_observed`

---

## 3. CLI Reference

All commands are run as `python -m experience_rate <subcommand>`.
The `--config` option switches the path to `EAS/config.yaml`.

### 3.1 scalebb-fit (Phase 1)

2D smoothing of observed rates + improvement-rate extraction → load into DB.

```powershell
python -m experience_rate scalebb-fit `
    --source mortality `
    --disease cancer heart_disease cerebrovascular `
    --sex total `
    --age-min 20 --age-max 89 `
    --year-min 1990 `
    --lam-row 40 --lam-col 40
```

Output: `data/processed/scalebb_fit.parquet` (overwritten) / the `scalebb_improvement` table.

### 3.2 scalebb-project (Phase 2)

Converge linearly to the long-term rate L and project into the future up to the horizon year.

```powershell
python -m experience_rate scalebb-project `
    --long-term-rate 0.01 `
    --convergence-year 2035 `
    --horizon 2050
```

By default, `data/processed/scalebb_fit.parquet` is used as the input.
An arbitrary fit result can be specified with `--fit-file <path>`.

### 3.3 scalebb-heatmap (visualization)

Outputs per-disease heatmaps (observed / smoothed / BB blended) and
per-age rate trajectories (log scale) as PNG files.

```powershell
python -m experience_rate scalebb-heatmap `
    --source mortality `
    --disease cancer heart_disease cerebrovascular `
    --sex total --age-min 20 --age-max 89 --year-min 1990 `
    --long-term-rate 0.01 --convergence-year 2035 --horizon 2050
```

Default output directory: `EAS/output/scalebb_figures/*.png`.

### 3.4 scalebb-runs

List the run history.

```powershell
python -m experience_rate scalebb-runs --last 20
```

### 3.5 scalebb-load

Load existing fit/projection CSV/Parquet files into the DB after the fact
(e.g. to import results computed on another machine into EAS).

```powershell
python -m experience_rate scalebb-load --kind fit --file data/processed/scalebb_fit.parquet
python -m experience_rate scalebb-load --kind projection --file data/processed/scalebb_projection.parquet
```

## 4. Typical Workflows

### 4.1 Initial setup

```powershell
cd c:\Github\IAJ_IT\EAS
pip install -r requirements.txt        # includes numpy, scipy, matplotlib, seaborn
python -m experience_rate --config config.yaml init
```

### 4.2 Combined projection for all diseases × sex total

```powershell
# 1) Fit
python -m experience_rate scalebb-fit `
    --source mortality --disease cancer heart_disease cerebrovascular `
    --sex total --age-min 20 --age-max 89 --year-min 1990

# 2) Project
python -m experience_rate scalebb-project `
    --long-term-rate 0.01 --convergence-year 2035 --horizon 2050

# 3) Heatmap
python -m experience_rate scalebb-heatmap `
    --source mortality --disease cancer heart_disease cerebrovascular `
    --sex total --age-min 20 --age-max 89 --year-min 1990 `
    --long-term-rate 0.01 --convergence-year 2035 --horizon 2050

# 4) Check
python -m experience_rate summary
python -m experience_rate scalebb-runs --last 10
```

### 4.3 Example SQL queries on the results

```sql
-- Get the latest projection run
SELECT run_id FROM scalebb_run
WHERE kind = 'projection'
ORDER BY created_at DESC LIMIT 1;

-- Cancer, age 60: compare projected rates in 2020 vs 2040
SELECT age, year, rate_projected, improvement_final, is_observed
FROM scalebb_projection
WHERE run_id = :run_id
  AND disease_id = 'cancer'
  AND age = 60
  AND year IN (2020, 2040)
ORDER BY year;
```

---

## 5. How to Choose the Main Parameters

| Parameter | Default | Guidance |
|---|---|---|
| `lam_row` / `lam_col` | 40 / 40 | Smoothing strength in the age / calendar-year directions. Comparable to the original Report. For noisy small categories, increase to 80-100 |
| `long_term_rate` L | 0.01 (1%) | Long-term annual improvement rate. SOA Scale BB uses 1% as the default. Sensitivity analysis over 0.005-0.02 is recommended depending on disease characteristics |
| `convergence_year` P | 2035 | Year by which the observed improvement rate fully converges to L. The original Scale BB report used 2027 |
| `horizon` | 2050 | Final projection year. Align with the policy-reserve valuation horizon of the main insurance products |
| `age_min` / `age_max` | **20 / 89** | Also covers products for younger ages. Ages 20 and above are continuous in 5-year age groups with no gaps in the mortality panel. A separate model is recommended for children (0-14) |

---

## 6. Troubleshooting

| Symptom | Cause | Remedy |
|---|---|---|
| `FileNotFoundError: scale_bb_disease.py` | EAS cannot locate the repo root | Check that `REPO_ROOT` is resolved correctly at the top of `EAS/src/experience_rate/scalebb.py` |
| `IndexError: index N is out of bounds` | NaN columns are dropped during pivot and the matrix dimensions mismatch | The `_pivot()` helper in `scale_bb_disease.py` already reindexes the full age×year grid. Take care not to reintroduce this when making custom modifications |
| Nothing shows up in `scalebb_run` | Ran with `load_to_db=False` / a different DB file is in use | Check `paths.database` in `config.yaml` |
| No figures are produced | No PNG files in `EAS/output/scalebb_figures` | Run `scalebb-heatmap` first |

---

## 7. File Inventory

| Kind | Path |
|---|---|
| DB schema | `EAS/sql/01_schema.sql` (last 3 tables) |
| EAS wrapper | `EAS/src/experience_rate/scalebb.py` |
| CLI | `EAS/src/experience_rate/cli.py` (`scalebb-*` subcommands) |
| Core algorithm | `scripts/scale_bb_model.py` |
| fit/project CLI | `scripts/scale_bb_disease.py` |
| Visualization | `scripts/visualize_scale_bb_heatmaps.py` |
| Output (fit/proj) | `data/processed/scalebb_{fit,projection}.parquet` |
| Output (figures) | `EAS/output/scalebb_figures/*.png` |
| Theoretical background | `PDF/researchmortalityimprovebbreport.pdf`, `data/summary/abstract_draft_v2_ja.md` |
