[日本語](README.md) | **English**

# cohort_power — Estimator of a pandemic cohort effect and power analysis (paper §3.4, §7.3)

*English version of [README.md](README.md). If the versions disagree, the Japanese version is authoritative.*

This package takes the original question of the study — did the pandemic leave a lasting, generation-specific change in later incidence rates? — as far as the public data allow, and states which data would test it.

## Estimator (paper Eq. 3.9)

    log m(x, y) = a_x + g_x * y + b_y + theta * C(x, y) + e(x, y)

Fitted by WLS with event counts as weights on the pre-shock years (2010–2019) and the post-shock years (2023 onwards); 2020–2022 are left out. `C` is the share of the cell that belongs to the exposed cohorts (born 1981–2000, aged 20–39 in 2020) in the post-shock years. The effect is attributed to the cohort when `C` fits better (lower weighted SSE) than a regressor for attained ages 20–39.

## Scripts

| Script | What it does | Output |
|---|---|---|
| `apply_public_data.py` | Applies the estimator to the 14 series of 7 causes × men and women (5-year groups 20–85, 2010–2019 + 2023–2024, death-count weights) | `output/public_data_theta.csv` (theta, 95% interval, whether the cohort regressor fits better) |
| `run_power.py` | Power on synthetic data: age granularity (5-year / single) × post-shock years (2 / 5 / 10) × exposure (national 1.5 million / large insurer 100,000 / small insurer 10,000 person-years per single age) × design (aggregate / individual follow-up) × effect δ (0, 0.05, 0.10, 0.20), 200 replicates each, over-dispersion φ = 2.5 | `output/power_long.csv` (per replicate), `output/power_summary.csv` (power, attribution, theta_mean, theta_sd, threshold) |

The detection threshold is the 95th percentile of theta under δ = 0 for the same condition (false-positive rate 5%).

## Running

```bash
cd reproduction/cohort_power
OPENBLAS_NUM_THREADS=1 python apply_public_data.py      # seconds
OPENBLAS_NUM_THREADS=1 python run_power.py --reps 200   # tens of minutes (seed 20260930)
```

The input panel is `../backtest/data/disease_panel_mortality.csv` (built by `../backtest/build_panel.py`), or the bundled `prebuilt_disease_panel_mortality.csv` if it is absent.

## Reuse on an insurer's own data

Give `fit()` in `apply_public_data.py` the claim counts and exposure of an incidence panel to run the same estimate. With individual follow-up of infection (or any exposure event), split the post-shock cells into exposed and unexposed persons and use the regression of `design="tracked"` in `run_power.py` (a main effect of exposure plus C × exposure). Setting `EXPOSURES` to the insurer's own scale gives a guide to the number of post-shock years needed.

## Limits

The simulation assumes the estimator's model (linear age-specific trends, a common period effect) to be right, so the power figures are upper bounds. The exposed cohorts are fixed in advance; a search over age bands needs a correction for multiplicity (paper §10, item 5).
