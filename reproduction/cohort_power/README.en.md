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
| `apply_public_data.py` | Applies the estimator to the 14 series of 7 causes × men and women (5-year groups 20–85, 2010 and 2013–2019 + 2023–2024, death-count weights), with two-sided p-values and Holm and Benjamini–Hochberg adjustments over the 14 series (also without hypertensive) | `output/public_data_theta.csv` |
| `public_panel_power.py` | Simulates each of the 14 series with the public panel's own structure (population by sex and age group, pre-shock base rates and age trends, year-effect standard deviation, dispersion) and measures the power of the same estimator (paper Table 7.2) | `output/public_panel_power.csv`, `output/public_panel_structure.csv` |
| `run_power.py` | A grid that separates data structure from exposure size (paper Table 7.3): age granularity (5-year / single) × post-shock years (2 / 5 / 10) × exposure (person-years per single age: national 1.5 million / intermediate / small 10,000; the intermediate level is a hypothetical value between the two, not the size of any insurer) × design (aggregate / individual follow-up) × effect δ (0.05, 0.10, 0.20), over-dispersion φ = 2.5 | `output/power_summary.csv` (with `--long`, one row per replicate in `output/power_long.csv.gz`) |

Replicates (third review, A-15): for every condition, 2,000 null replicates set the detection threshold (95th percentile of theta), an independent 2,000 null replicates measure the false-positive rate, and 2,000 replicates per effect size measure detection and attribution, each with a 95% Wilson interval for the Monte Carlo error. Each condition runs on its own random stream (`SeedSequence.spawn`), in parallel.

## Running

```bash
cd reproduction/cohort_power
OPENBLAS_NUM_THREADS=1 python apply_public_data.py        # seconds
OPENBLAS_NUM_THREADS=1 python public_panel_power.py       # about 5 minutes on 16 cores (seed 20261001)
OPENBLAS_NUM_THREADS=1 python run_power.py                # about 10 minutes on 16 cores (seed 20260930)
```

The input panel is `../backtest/data/disease_panel_mortality.csv` (built by `../backtest/build_panel.py`), or the bundled `prebuilt_disease_panel_mortality.csv` if it is absent.

## Reuse on an insurer's own data

Give `fit()` in `apply_public_data.py` the claim counts and exposure of an incidence panel to run the same estimate. With individual follow-up of infection (or any exposure event), split the post-shock cells into exposed and unexposed persons and use the regression of `design="tracked"` in `run_power.py` (a main effect of exposure plus C × exposure). Setting `EXPOSURES` to the insurer's own scale gives a guide to the number of post-shock years needed. The follow-up design assumes that the infected and the uninfected differ only by infection (no confounding by the capture of infection records, underwriting selection, vaccination or lapses).

## Limits

The simulation assumes the estimator's model (linear age-specific trends, a common period effect) to be right, so the power figures are upper bounds. On the public panel the simulated spread of theta is 70–90% of the real standard errors: the real data are noisier. The exposed cohorts are fixed in advance; a search over age bands needs a correction for multiplicity (paper §10, item 5).
