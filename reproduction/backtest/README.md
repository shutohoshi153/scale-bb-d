# backtest — §3 backtest reproduction package

This directory is a self-contained package that reproduces the **backtest** of
paper §3 ("Data and Methodology"): point-forecast accuracy and directional
accuracy. It regenerates every artifact of §5 (point forecasts) and §6
(directional accuracy) in one shot, starting from the raw Vital Statistics
table 5-15.

It depends on nothing outside this directory — all input data and the
algorithm core are bundled.

> One of the two packages under `reproduction/`. Its sister package
> `../generational/` (APC generational assumed-rate tables, §3.3; see
> `../generational/README.md`) shares the same algorithm core and input
> mortality data. See `../README.md` for the overall division of work.

---

## Quick start

```bash
bash run_all.sh

# or with an explicit Python interpreter
PY=/path/to/python bash run_all.sh
```

Finishes in a few minutes; all artifacts are generated under `./output/`.

**Dependencies:** Python 3.10+ with `pandas`, `numpy`, `scipy`, `matplotlib`.

---

## Package layout

```
backtest/
├── run_all.sh                       one-shot reproduction driver (full §3 pipeline)
├── _paths.py                        self-contained path layer (see "Modifications" below)
├── build_panel.py                   [1] table 5-15 → disease panel (§3.1)
├── run_backtest.py                  [2] Scale BB-D fit/projection + validation (§3.2)
├── run_baselines.py                 [3] naive / mean_3pts / loglin baselines (§3.4.1)
├── compute_directional_accuracy.py  [4] directional accuracy DA (§3.4.2, eqs. 3.11–3.12)
├── compare_cutoffs.py               [5] cross-cutoff comparison (§4)
├── make_calibration_recovery_figure.py  [6] recalibration experiment for direction-reversing
│                                        diseases (§6.5, Figure 6.3)
├── make_paper_figures.py            [7] generate/collect the figures that appear in the paper
│                                        (→ ../../figures/)
├── vendor/
│   └── experience_rate/_scalebb_core/
│       ├── model.py                 Scale BB core (§3.2, eqs. 3.1–3.6)
│       └── apc_model.py             APC extension (§3.3, eqs. 3.7–3.8)
├── data/
│   ├── raw/estat_5-15_deaths_by_cause_sex_age_0003411659.csv
│   │                                input: Vital Statistics table 5-15 (1950–2024)
│   └── prebuilt_disease_panel_mortality.csv   expected output of build_panel (for checking)
└── output/                          [generated] rebuilt by run_all.sh (not tracked by git)
```

## Execution order and mapping to §3

`run_all.sh` runs the following in order.

| # | Script | Output | Paper section |
|---|---|---|---|
| 1 | `build_panel.py` | `data/disease_panel_mortality.csv` (8 diseases × 3 sexes × 25 years × 21 age groups = 12,600 rows) | §3.1 data and disease mapping |
| 2 | `run_backtest.py` (cutoffs 2014/2021/2022) | `output[/cutoff_*]/tables/validation_summary.csv` etc. | §3.2 Scale BB-D fit/projection, eqs. (3.1)–(3.6) |
| 3 | `run_baselines.py` (same 3 cutoffs) | `output[/cutoff_*]/tables/validation_summary_baseline.csv` etc. | §3.4.1 baselines; §3.4.2 MAPE/bias (eqs. 3.9–3.10) |
| 4 | `compare_cutoffs.py` | `output/cutoff_comparison/` | §4 validation design (across 3 cutoffs) |
| 5 | `compute_directional_accuracy.py` | `output/directional/` | §3.4.2 directional accuracy DA (eqs. 3.11–3.12) → §6 |
| 6 | `make_calibration_recovery_figure.py` | `output/directional/tables/calibration_recovery.csv`, Figure 6.3 (committed) | §6.5 recalibration experiment for direction-reversing diseases (liver / hypertensive; re-set L and P × cutoff) |
| 7 | `make_paper_figures.py` | `../../figures/` (committed) | explanatory figures of §3–§4 and collection of the result figures referenced by §5–§6 |

## Expected reference numbers (ground truth for checking)

A correct run can be confirmed against the following representative values
(`sex=total`; they match the tables of §5 and §6 of the paper).

**Scale BB-D MAPE [%]** (`output/cutoff_comparison/tables/scalebb_cutoff_comparison.csv`)

| disease | 2014 | 2021 | 2022 |
|---|---:|---:|---:|
| cancer | 22.41 | 9.20 | 8.87 |
| total | 26.01 | 9.33 | 7.33 |
| hypertensive | 73.83 | 24.13 | 20.53 |

**Directional accuracy DA [%]** (`output/directional/tables/directional_summary.csv`, cutoff=2014)

| disease | scalebb | naive_last | loglin_trend |
|---|---:|---:|---:|
| total | 95.00 | 0.00 | 94.29 |
| cerebrovascular | 91.04 | 0.00 | 91.04 |
| cancer | 79.71 | 0.00 | 93.48 |

`naive_last` has DA = 0.00 in every cell by construction: its predicted change
is identically zero ($\Delta_{\text{pred}} \equiv 0$, eq. 3.11), so it carries
no direction information — exactly as described in §3.4.2.

## Modifications relative to the research-side scripts (for transparency)

The bundled analysis scripts do **not** modify any algorithm, aggregation or
plotting logic of the original research scripts. The only modification is the
few path-anchor lines at the top of each file (marked `# [REPRO]`), which now
resolve all inputs through the bundled `_paths.py` instead of research-side
directories that are not part of this repository.

`vendor/experience_rate/_scalebb_core/` is an unmodified copy of the algorithm
core shared with `../generational/` — the implementation corresponding
one-to-one to the equations of §3.2/§3.3. (Comments and docstrings throughout
the package were translated to English for this public repository; code paths
and logic are unchanged, and outputs are verified identical.)

## Data sources and license

- **Vital Statistics table 5-15** (e-Stat statistical table ID 0003411659):
  source — Vital Statistics of Japan, Ministry of Health, Labour and Welfare
  (e-Stat). Redistributed and reused with attribution under the Government of
  Japan Standard Terms of Use v2.0.
- See `../../DATA_SOURCES.md` for the full citation and terms.
- This package is an academic validation based on public data; it does not
  guarantee the profitability or capital requirements of any specific
  insurance product (see paper §10).
