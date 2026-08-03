# reproduction — §3 reproduction packages

This directory packages the validation pipeline of paper §3 ("Data and
Methodology") in a form that can be re-run and verified standalone. It
consists of **two complementary packages** that together cover all of §3.

Section numbers (§) refer to the paper distributed by the ICA 2026 organisers;
the manuscript itself is not part of this repository.

```
reproduction/
├── README.md        ← this file (division of work and consistency)
├── backtest/        point-forecast accuracy + directional accuracy   (§3.1 / §3.2 / §3.4 / §5 / §6)
└── generational/    APC generational assumed-rate table pipeline     (§3.3)
```

## Division of work

| Package | Reproduces | Runner | Input | Main output |
|---|---|---|---|---|
| **`backtest/`** | Backtest: 3 cutoffs × Scale BB-D × 3 baselines — point-forecast MAPE (eqs. 3.9–3.10) and directional accuracy DA (eqs. 3.11–3.12) | standalone scripts (`run_all.sh`) | Vital Statistics table 5-15 (bundled) | validation tables and figures under `output/` |
| **`generational/`** | APC fit/projection → per-issue-year 1D assumed-rate tables (generational projection) | `experience_rate` CLI | `mortality_apc_panel` (bundled) | assumed-rate tables checked against `reference_output/` |

`backtest/` tests whether Scale BB-D is suitable for point forecasts
(conclusion: it loses on MAPE but gets the direction right), while
`generational/` runs the same improvement-rate framework forward to produce
assumed-rate tables in the format used in practice. The scopes do not overlap.

## Consistency between the two packages (verified)

1. **Identical algorithm core.** `backtest/vendor/experience_rate/_scalebb_core/`
   and `generational/KDB/src/experience_rate/_scalebb_core/` are identical
   copies. Both packages use the same Scale BB / APC implementation
   (§3.2 eqs. 3.1–3.6, §3.3 eqs. 3.7–3.8).
2. **Identical input mortality data.** Both start from the cause-specific
   mortality rates of the e-Stat Vital Statistics; shared cells
   (cancer / cerebrovascular / heart / hypertensive / total) match exactly.
3. **Common two-layer framing of the data.** Cause-specific mortality is used
   (i) as a proxy for medical-insurance incidence rates and (ii) as the direct
   assumption for disease-contingent death benefits (§3.1.3).
4. **Common core hyperparameters.** `long_term_rate=0.01`,
   `convergence_year=2035`, `lam_row=40`, `diff_order=2`.

### Setting differences (by use case, not contradictions)

| Item | `backtest/` | `generational/` | Note |
|---|---|---|---|
| `lam_col` (calendar-year smoothing) | 40 | 60 | backtest follows the KDB default; generational uses 60 to suppress noise at young ages under the age20 preset (§3.2.3 footnote) |
| Age range | 20–89 | 20–85 (age20 preset) | minor, setting-dependent difference |

> Both packages use the same disease slug `heart_disease`
> (code Hi05, heart disease excluding hypertensive).

## Usage

```bash
# Backtest (regenerates all artifacts in a few minutes)
cd backtest && bash run_all.sh

# Generational assumed-rate tables (CLI; details in generational/README.md)
cd generational/KDB && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && export PYTHONPATH=src
python -m experience_rate scalebb-apc-fit --source mortality --sex male \
  --disease cancer heart_disease cerebrovascular --use-preset --run-id male_repro
```

For details, expected reference numbers and the list of modifications relative
to the research-side scripts, see `backtest/README.md` and
`generational/README.md`.

## Data sources

Citations and terms of use for the bundled third-party data are collected in
`../DATA_SOURCES.md`.
