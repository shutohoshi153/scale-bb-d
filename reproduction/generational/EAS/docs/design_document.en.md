[日本語](設計書.md) | **English**

# Disease Incidence Rate Panel Design Document (Reproduction Environment Edition)

*English translation of [設計書.md](設計書.md) (as of 2026-08-05). If the versions disagree, the Japanese version is authoritative.*

> **Scope of this document**
> The original design document covered the entire experience-rate (A/E) analysis
> system for individual medical insurance. This reproduction environment uses no
> actual in-force, movement, or claims data and does not perform experience-rate
> analysis, so the corresponding features (the `ins_*` tables, the YAML-driven
> importer, `analyze` / `analyze-benchmark`, and the Web UI) are excluded from the
> distribution. Accordingly, this document describes **only the pipeline that
> builds the disease incidence rate panel from population statistics**.
> For the original document including the excluded parts, see
> `ICA/ValidationTools/EAS/docs/設計書.md`.

## 1. Purpose and Scope

The purpose is to build, under a unified schema, incidence rate panels by disease,
sex, and age group from e-Stat (Patient Survey, Vital Statistics) and the National
Cancer Registry, and to supply them as inputs to the Scale BB / APC extended model.

- Normalize multiple rates (`rate_type`) with different sources and quality levels into a single table
- Make the quality of each source explicit via a `quality_flag` so downstream consumers can filter on it
- Fully self-contained on SQLite, with no dependency on external RDBMSs such as SQL Server

## 2. System Architecture

| Layer | Implementation | Responsibility |
| --- | --- | --- |
| Data layer | SQLite (`experience_rate.db`) | Persistence of `population_incidence` / `rider_def` / `scalebb_*`, etc. |
| Panel-building layer | `scripts/build_*_panel.py` | Raw data → generation and integration of the panel CSVs for each `rate_type` |
| Model layer | `src/experience_rate/_scalebb_core/` | 2D Whittaker-Henderson smoothing, APC decomposition, generational projection |
| UI layer | CLI (`cli.py`) | Interactive operation, result display, CSV export |

## 3. Data Model

Defined in `sql/01_schema.sql`.

| Table | Purpose |
| --- | --- |
| `parameters` | Single row holding the observation-year end month and fiscal-year end month |
| `rider_def` | Rider master (`rider_code` / `rider_name` / `rider_category` / `description`) |
| `population_incidence` | Population incidence rate panel (rate_type × disease × year × sex × age) |
| `rider_disease_map` | Mapping between riders and disease incidence rates |
| `scalebb_run` | Scale BB / APC run metadata (parameters stored in `config_json`) |
| `scalebb_improvement` | Fit results (observed rates, smoothed rates, and improvement rates by age × year) |
| `scalebb_cohort_effect` | APC cohort effects γ |
| `scalebb_projection` | Projection results (improvement rates, projected rates, and observed flag by age × year) |
| `predicted_rate_generational` | Issue-year-specific 1D assumed incidence rate tables |

> `rider_def` / `rider_disease_map` form the correspondence table between riders and
> diseases; in this environment, which carries no policy data, they serve only as
> reference metadata for the incidence rates.

## 4. Data Flow

```
        data/RowData/  (raw data from e-Stat / the National Cancer Registry)
                │
                ▼   scripts/build_*_panel.py
        data/processed/  (panel CSVs for each rate_type)
                │
                ▼   scripts/build_incidence_panel.py
        incidence_panel.csv / parquet
                │
                ▼   experience_rate load-incidence
        population_incidence  (SQLite)
                │
                ▼   scalebb-apc-fit → scalebb-apc-project → scalebb-gen-table
        predicted_rate_generational / issue-year-specific assumed incidence rate CSVs
```

## 5. Disease Incidence Rate Data Sources

| `rate_type` | Source | Quality | Coverage period | Use |
| --- | --- | --- | --- | --- |
| `registry` | National Cancer Registry (NCR) | **A** (true incidence) | 2016-2023 | highest-quality benchmark for cancer incidence rates |
| `initial_visit` | Patient Survey Z70 (initial outpatient consultation rate) | B (approximation) | 2023 cross-section | lifestyle diseases / initial-visit flow |
| `discharge` | Patient Survey Z10 + H20-47 average length of stay | C (approximation) | 2023 cross-section | hospitalization-benefit riders |
| `mortality` | Vital Statistics 5-15 (crude death rate) | D (lower bound) | 1950-2020 | lower bound for fatal diseases. **Input to the assumed incidence rate tables** |

### 5.1 Formula for Each rate_type

- **registry**: age-group incidence counts from the National Cancer Registry ÷ Japanese population (directly a per-person-year rate).
- **initial_visit**: the Z70 "initial outpatient consultation rate per 100,000 population per survey day",
  converted to an annual rate.
  - `rate_per_year ≒ rate_per_100k × config.incidence.initial_visit_annual_days
    / 100,000 × config.incidence.initial_visit_duplicate_adjust`
- **discharge**: annual rate derived from Z10 discharge counts × 365 ÷ length of stay, converted to the population denominator.
- **mortality**: crude death rate (per 100,000) from Vital Statistics converted to a per-person-year rate.

> Note that the input to the assumed incidence rate tables is `mortality`
> (cause-of-death-specific mortality rates).
> `registry` is not an input; it is used as the A-tier benchmark for true incidence.
> For details, see `../../README.md` §1 one level up.

## 6. Known Limitations

| Item | This reproduction environment |
| --- | --- |
| Incidence-rate proxy | Cause-of-death-specific mortality rates are used as a proxy for disease incidence rates (the gap versus true incidence remains future work) |
| `initial_visit` / `discharge` | Single 2023 cross-section only. Insufficient as input to time-series models |
| Age groups | 5-year age groups by default. Single ages are generated by the log-linear interpolation in `scalebb-gen-table` |
| Experience-rate (A/E) analysis | Out of scope, since no policy data is handled (the feature itself is excluded) |

## 7. Testing and Verification

```bash
export PYTHONPATH=src

# 1. Initialize the DB + load the incidence rate panel
python -m experience_rate init --drop
python -m experience_rate load-incidence
python -m experience_rate summary

# 2. Consistency check against the standard life table (input-data validity check)
python scripts/analyze_standard_life_table.py

# 3. Reproduce the assumed incidence rate tables and compare with the reference outputs
#    → see ../../README.md §4-§5 for the procedure
```
