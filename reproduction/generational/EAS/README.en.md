[日本語](README.md) | **English**

# Expected Incidence Rate Table Generation Environment (SQLite + Python)

*English translation of [README.md](README.md) (as of 2026-08-05). If the versions disagree, the Japanese version is authoritative.*

A **SQLite + Python reproduction environment** responsible for building the
population-based incidence rate panel and generating assumed incidence rate
tables with the **Scale BB / APC extended model**.

> **Scope of this reproduction environment**
> This study does not use any actual in-force, movement, or claims data,
> nor does it use experience-rate (A/E) analysis. Therefore, the components of
> the original system that depend on them — the individual medical insurance
> importer (`ins_*` tables / `import-*` commands), experience-rate analysis
> (`analyze` / `analyze-benchmark`), and the Web UI (`serve`) — are
> **excluded from this distribution**. What is included is only the pipeline
> whose sole inputs are population statistics (e-Stat / National Cancer
> Registry).

## Features

- **Self-contained on SQLite**: runs with no external services (dependencies: pandas / PyYAML / tabulate / pyarrow / xlrd / openpyxl)
- **Disease incidence rate panel**: four incidence rate types (`registry` / `initial_visit` /
  `discharge` / `mortality`) computed from population data (e-Stat Patient Survey,
  Vital Statistics, and the National Cancer Registry), stored in the
  `population_incidence` table
- **Scale BB extended model**: an extension of the SOA (2012) Mortality Improvement
  Scale BB applied to disease incidence/mortality rates. Improvement-rate extraction
  via 2D Whittaker-Henderson smoothing and future projection via a linear-convergence
  blend toward the long-term rate L, all runnable from the CLI
  (persisted in `scalebb_run` / `scalebb_improvement` / `scalebb_projection`)
- **APC extension + generational projection**: cohort-penalized APC decomposition and
  generation of issue-year-specific 1D assumed incidence rate tables
  (`predicted_rate_generational`)

## Project Layout

```
EAS/
├── README.md                       # this file
├── requirements.txt
├── config.yaml                     # settings such as the observation-year end month
├── sql/
│   └── 01_schema.sql               # table DDL (parameters / rider_def / incidence / scalebb)
├── src/
│   └── experience_rate/
│       ├── __init__.py
│       ├── __main__.py
│       ├── db.py                   # connection / initialization utilities
│       ├── etl.py                  # incidence panel loading (equivalent of sp_etl)
│       ├── cli.py                  # CLI entry point
│       ├── scalebb.py              # Scale BB (AP) wrapper
│       ├── scalebb_apc.py          # APC extension wrapper
│       ├── scalebb_gen.py          # generational projection table generation
│       └── _scalebb_core/          # algorithm core (2D WH / cohort penalty / projection)
├── scripts/
│   ├── panel_helpers.py            # shared helpers for building disease panels
│   ├── build_mortality_incidence_panel.py  # Vital Statistics-based incidence rates
│   ├── build_initial_visit_panel.py        # based on Z70 (initial outpatient consultation rate)
│   ├── build_cancer_registry_panel.py      # based on the National Cancer Registry (highest quality)
│   ├── build_los_panel.py                  # average length-of-stay panel
│   ├── build_discharge_panel.py            # discharge flow (Z10÷LOS×365)
│   ├── build_incidence_panel.py            # merges the above into incidence_panel
│   └── analyze_standard_life_table.py      # consistency check against the standard life table
├── data/
│   ├── RowData/                    # National Cancer Registry (NCR) source files
│   ├── lifetable/                  # standard life table (for consistency checks)
│   └── processed/                  # incidence_panel / mortality_apc_panel / rider_disease_map, etc.
└── docs/
    ├── 設計書.md
    └── Scale_BB機能.md              # CLI/DB specification of the Scale BB extended model
```

## Setup

```powershell
# Install dependencies (pandas + PyYAML + tabulate + fastapi + uvicorn ...)
pip install -r requirements.txt
```

## Quick Start

```powershell
# 1. Initialize the DB (deletes any existing file)
$env:PYTHONPATH = "src"
python -m experience_rate init --drop

# 2. Build the disease incidence rate panel (incidence_panel) and load it into the DB
python -m experience_rate build-incidence       # e-Stat/NCR → incidence_panel.csv
python -m experience_rate load-incidence        # incidence_panel → population_incidence

# 3. Check the row-count summary
python -m experience_rate summary

# 4. APC fit → projection → issue-year-specific assumed incidence rate tables
python -m experience_rate scalebb-apc-fit --source mortality --sex male `
    --disease cancer heart_disease cerebrovascular --use-preset
python -m experience_rate scalebb-apc-project `
    --fit data/processed/scalebb_apc_fit_male.parquet --use-preset
python -m experience_rate scalebb-gen-table --use-preset `
    --output-dir data/processed/predicted_rate
```

> For the complete reproduction procedure for the assumed incidence rate tables
> (both sexes × 3 diseases, comparison against the reference outputs), see
> [`../README.md`](../README.md) §4 one level up.

## Main Commands

| Command | Description |
| --- | --- |
| `init --drop` | Initialize the SQLite DB (build schema + insert parameters) |
| `summary` | Show the row count of each table |
| `build-incidence` | Build the disease incidence rate panel (`incidence_panel.csv/parquet`) from e-Stat + the National Cancer Registry |
| `load-incidence --data-dir DIR` | Load the disease incidence rate panel and `rider_disease_map.csv` into the DB |
| `export-incidence --output FILE [--rate-type ...] [--disease ...] [--year N] [--sex 0/1/2]` | Export a filtered CSV from `population_incidence` |
| `scalebb-fit --source ... --disease ... --age-min N --age-max M` | Run Scale BB Phase 1 (2D smoothing + improvement-rate extraction) and load into the DB |
| `scalebb-project --long-term-rate L --convergence-year P --horizon Y` | Run Scale BB Phase 2 (long-term-rate blend + future projection) and load into the DB |
| `scalebb-heatmap --source ... --disease ...` | Output Scale BB-style heatmaps/projection figures (PNG) to `output/scalebb_figures/` |
| `scalebb-apc-fit --source ... --sex ... --disease ... [--use-preset]` | Run the APC extension (cohort penalty + γ cohort effects + COVID dummies) and load into the DB |
| `scalebb-apc-project --fit PATH [--use-preset]` | Blend the APC fit results toward the long-term rate L, project into the future, and load into the DB |
| `scalebb-gen-table --run-id ID [--use-preset] --output-dir DIR` | Generate issue-year-specific 1D assumed incidence rate tables via generational projection |
| `scalebb-runs [--last N] [--kind fit/projection]` | Show the `scalebb_run` history |
| `scalebb-load --kind fit/projection --file PATH` | Load existing fit/projection CSV/Parquet files into the DB after the fact |

## Disease Incidence Rate Data Sources

| `rate_type` | Source | Quality | Coverage period | Use |
| --- | --- | --- | --- | --- |
| `registry` | National Cancer Registry (NCR) | **A** (true incidence) | 2016-2023 | benchmark for cancer riders |
| `initial_visit` | Patient Survey Z70 (initial outpatient consultation rate) | B (approximation) | 2023 cross-section | lifestyle diseases / initial-visit flow |
| `discharge` | Patient Survey Z10 + H20-47 average length of stay | C (approximation) | 2023 cross-section | hospitalization-benefit riders |
| `mortality` | Vital Statistics 5-15 (crude death rate) | D (lower bound) | 1950-2020 | base-policy mortality / fatal diseases |

For the details and formulas of each rate_type, see [`docs/設計書.md`](./docs/設計書.md)
(English translation: [`docs/design_document.en.md`](./docs/design_document.en.md)).

## Scale BB Extended Model

The SOA (2012) Mortality Improvement Scale BB, extended and applied to disease
incidence/mortality rates, can be run and persisted from within EAS.
The algorithm itself lives in `scripts/scale_bb_model.py` (repo root);
the EAS side acts as a thin wrapper (`src/experience_rate/scalebb.py`).

### Workflow (CLI)

```powershell
$env:PYTHONPATH = "src"

# 1) Fit: 2D Whittaker-Henderson smoothing of observed rates → improvement-rate extraction → load into DB
python -m experience_rate scalebb-fit `
    --source mortality `
    --disease cancer heart_disease cerebrovascular `
    --sex total --age-min 20 --age-max 89 --year-min 1990

# 2) Project: converge to long-term rate L=1% by 2035, project to 2050
python -m experience_rate scalebb-project `
    --long-term-rate 0.01 --convergence-year 2035 --horizon 2050

# 3) Heatmap: per-disease age×year improvement-rate heatmaps (PNG)
python -m experience_rate scalebb-heatmap `
    --source mortality `
    --disease cancer heart_disease cerebrovascular `
    --sex total --age-min 20 --age-max 89 --year-min 1990 `
    --long-term-rate 0.01 --convergence-year 2035 --horizon 2050

# 4) Check the history
python -m experience_rate scalebb-runs --last 10
```

### Storage Tables

| Table | Contents |
| --- | --- |
| `scalebb_run` | Run metadata (kind, source, diseases, λ, L, P, horizon, config_json, created_at) |
| `scalebb_improvement` | Phase 1 results: age × year × (rate_observed, rate_smoothed, improvement_observed, improvement_smoothed) |
| `scalebb_projection` | Phase 2 results: age × year (observed + projected) × (improvement_final, rate_projected, is_observed) |

For the detailed specification, DB schema, and troubleshooting, see
[`docs/Scale_BB機能.md`](./docs/Scale_BB機能.md)
(English translation: [`docs/Scale_BB_features.en.md`](./docs/Scale_BB_features.en.md)).
