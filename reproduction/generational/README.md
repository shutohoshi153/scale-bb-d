# generational — APC assumed-rate table pipeline (§3.3)

This package reproduces paper **§3.3 (the APC extension)** and its
forward-looking application: **generational projection**, i.e. generating
per-issue-year assumed-rate tables from cause-specific mortality. It is the
sister package of `../backtest/` (point-forecast accuracy and directional
accuracy, §3.4/§5/§6); the two share the same algorithm core
(`experience_rate/_scalebb_core/`) and input mortality data. See `../README.md`
for the overall division of work.

This is a **minimal distribution**: it contains exactly what is needed to
re-run the APC pipeline and verify the result against the bundled reference
output. Auxiliary features of the original research environment (experience
rate / A/E analysis on policy data, incidence-rate benchmarks from the
National Cancer Registry, standard-life-table validation, a Web UI) are not
part of this distribution.

## A note on the input data (to avoid misunderstanding)

The input is the **cause-specific mortality rates** of the Vital Statistics of
Japan (`KDB/data/processed/mortality_apc_panel.parquet`, derived from e-Stat;
see `../../DATA_SOURCES.md`). In the paper's framework these rates are used in
two layers: (i) as a **proxy** for incidence rates in medical insurance and
(ii) as the **direct assumption** for death benefits contingent on specific
diseases (§3.1.3). File names and labels that say "rate table" refer to rate
tables computed from cause-specific mortality throughout.

## Layout

| Path | Content |
| --- | --- |
| `KDB/` | self-contained runtime (SQLite + Python CLI): algorithm core, config, input panel |
| `KDB/src/experience_rate/_scalebb_core/` | Scale BB / APC algorithm core (2D Whittaker-Henderson smoothing, cohort penalty, generational projection) |
| `KDB/config.yaml` | parameter presets (shipped in the **age20** state: `age_min=20`, `issue_age=20`, `lam_col=60`) |
| `KDB/data/processed/mortality_apc_panel.parquet` | input panel: cause-specific mortality 1950–2024 (also bundled as `.csv`) |
| `reference_output/` | **reference outputs for verification** (snapshots generated on the research side) |
| `reference_output/predicted_rate_apc_age20/` | APC assumed-rate tables, issue_age=20 (matches the bundled config) |
| `reference_output/predicted_rate_apc/` | APC assumed-rate tables, issue_age=40 |
| `reference_output/scalebb_apc_*.parquet` etc. | fit / projection intermediates for comparison |

## Setup

Python 3.11+ is assumed. Everything is run from inside `KDB/`.

```bash
cd reproduction/generational/KDB
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=src

python -m experience_rate init --drop   # initialize the SQLite schema
```

## Reproduction steps

### Assumed-rate tables (APC version; per sex × 3 diseases)

```bash
# 1. APC fit (2D WH smoothing + cohort penalty + COVID dummy)
python -m experience_rate scalebb-apc-fit --source mortality --sex male \
  --disease cancer heart_disease cerebrovascular --use-preset --run-id male_repro

# 2. projection (improvement rates blended toward the long-term rate L, to 2100)
python -m experience_rate scalebb-apc-project \
  --fit data/processed/scalebb_apc_fit_male.parquet --use-preset --run-id male_repro_proj

# 3. generational tables (per-issue-year 1D [age]; log-linear single-age interpolation)
python -m experience_rate scalebb-gen-table --run-id male_repro_proj --use-preset \
  --output-dir data/processed/predicted_rate_repro

# For female, repeat with --sex female (and the female fit file in step 2).
```

**Note:** the bundled `config.yaml` is in the **age20 preset** state
(`age_min=20`, `issue_age=20`, `lam_col=60`); its output corresponds to
`reference_output/predicted_rate_apc_age20/`. To reproduce the issue_age=40
tables (`reference_output/predicted_rate_apc/`), set `age_min=40`,
`lam_col=40`, `issue_age=40` — either in `config.yaml` or via the
corresponding CLI arguments.

### CLI subcommands outside this distribution

`python -m experience_rate --help` lists the full command set of the original
tool. Only the commands used above (`init`, `scalebb-apc-fit`,
`scalebb-apc-project`, `scalebb-gen-table`, plus `summary` and `scalebb-runs`
for inspection) are usable here. The incidence-panel commands
(`build-incidence`, `load-incidence`, `export-incidence`) belong to the
incidence-benchmark path, whose input data and builder scripts are not part of
this minimal distribution; they will fail if invoked.

## Verification against the reference output

```bash
diff data/processed/predicted_rate_repro/predicted_rate_cancer_male_issue2026_ia20.csv \
     ../reference_output/predicted_rate_apc_age20/predicted_rate_cancer_male_issue2026_ia20.csv
```

On the research side this check (init → scalebb-apc-fit (cancer, male) →
scalebb-apc-project → scalebb-gen-table) matched the reference output on all
46 rows to ~15 significant digits (relative differences of ~1e-15 in the last
bit, attributable to floating-point summation order).

Other checks:

- `python -m experience_rate scalebb-runs --last 10` — audit run history and
  parameters (`config_json`)
- fit / projection intermediates can be compared against
  `reference_output/scalebb_apc_*.parquet`

## Relation to the paper

- The mathematical formulation of the APC extension (model equations and the
  identifiability discussion) is §3.3 of the paper.
- The hyperparameter differences relative to `../backtest/` (`lam_col=60`,
  age range 20–85) are use-case differences of the age20 preset, not
  contradictions; see `../README.md`.
