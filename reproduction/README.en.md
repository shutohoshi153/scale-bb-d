[日本語](README.md) | **English**

# reproduction — §3 Reproduction Packages (for Reviewers and Co-authors)

*English translation of [README.md](README.md) (as of 2026-08-31). If the versions disagree, the Japanese version is authoritative.*

This directory packages the validation pipeline of paper §3 "Data and Methods" and the §8 supplementary check (BEL sensitivity demonstration) in a form that can be reproduced and verified standalone.
It consists of **three complementary packages**, which together cover one end-to-end path: public data → fit and validation → scenario rate tables → projection and sensitivity table.

```
reproduction/
├── README.md        ← This file (division of roles and consistency)
├── backtest/        Point-forecast accuracy + directional accuracy validation   (§3.1 / §3.2 / §3.3 / §5 / §6)
├── generational/    APC generational assumed-rate table generation             (Appendix B; details in generational/README.md)
└── bel_demo/        Scenario generator → simple projection → sensitivity table   (§8, Appendix A; details in bel_demo/README.en.md)
```

## Division of Roles Between the Three Packages

| Package | What it reproduces | Runtime | Input | Main outputs |
|---|---|---|---|---|
| **`backtest/`** | Backtest: point-forecast MAPE (Eqs. 3.7–3.8) and directional accuracy DA (Eqs. 3.9–3.10) for 3 cutoffs × ScaleBB × 3 baselines | Standalone scripts (`run_all.sh`) | Vital Statistics table 5-15 (bundled) | Validation tables and figures under `output/` |
| **`generational/`** | APC fit/project → per-issue-year 1D assumed-rate tables (generational projection) | EAS CLI (`experience_rate`) | `mortality_apc_panel` (bundled) | Assumed-rate tables to be checked against `reference_output/` |
| **`bel_demo/`** | Scenario rate tables (6 scenarios, Phase 2 re-run only) → BEL projection (Eqs. 8.1–8.2) → Table 8.3, Figure 8.1, Table A.1 | Standalone scripts (`run_all.sh`) | Shares the panel and core with `backtest/`; FSA yield-curve tool (bundled) | Sensitivity table and figure under `output/`, checked against `reference_output/` |

`backtest/` tests "whether Scale BB is suited to point forecasting" (conclusion: it trails the best baseline by a few pp on MAPE but holds the direction),
`generational/` covers the stage of "running the improvement-rate framework forward to produce rate tables in a practice-ready distribution format,"
and `bel_demo/` covers the stage of "feeding those rate tables into a valuation model to obtain a regulatory-scenario sensitivity table."
Their scopes do not overlap.

## Consistency Between the Two Packages (Verified, 2026-07-22)

The following checks confirm that the shared directory is free of contradictions.

1. **Identical algorithm core**: `backtest/vendor/experience_rate/_scalebb_core/` and
   `generational/EAS/src/experience_rate/_scalebb_core/` are **bit-identical** (and also match the current EAS).
   Both packages use the same Scale BB / APC implementation (§3.2 Eqs. 3.1–3.6, Appendix B Eqs. B.1–B.2).
2. **Identical input mortality data**: both start from cause-of-death mortality rates from the e-Stat Vital Statistics (人口動態統計).
   For the shared cells (cancer / cerebrovascular / heart / hypertensive / total), an **exact match** (difference 0) was confirmed.
3. **Common position of the data**: cause-specific mortality is the assumption itself for death benefits contingent on
   specific diseases, and the claims of the paper are limited to that application (revised 2026-09-30; incidence rates of
   medical insurance are not treated, and an insurer can reuse `backtest/run_own_data.py` on its own experience).
4. **Common core hyperparameters**: `long_term_rate=0.01`, `convergence_year=2035`,
   `lam_row=40`, `diff_order=2`.

### Differences in Settings and Notation (Use-Case Differences, Not Contradictions)

| Item | `backtest/` | `generational/` | Notes |
|---|---|---|---|
| `lam_col` (calendar-year smoothing) | 20 | 60 | [Corrected 2026-09-30: 40 was a misprint; the value is 20, as in §3.2.3 of the paper and `SCALE_BB_CONFIG` of `run_backtest.py`; the authoritative record is `settings` in `backtest/output/MANIFEST.json`] backtest moved from 40 to 20 with the annual calendar grid (2026-09-02). generational uses 60 to suppress young-age noise after the age20 migration. Each is justified for its own use case (see the footnote in §3.2.3) |
| Age range | 20–89 | 20–85 (age20 preset) | Minor setting-dependent difference |

> The disease slug is unified as `heart_disease` (Hi05, heart diseases excluding hypertensive) in both packages.

## Usage

```bash
# Backtest (regenerates all artifacts in a few minutes)
cd backtest && bash run_all.sh

# Generational assumed-rate tables (EAS CLI; details in generational/README.md §3–4)
cd generational/EAS && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && export PYTHONPATH=src
python -m experience_rate scalebb-apc-fit --source mortality --sex male \
  --disease cancer heart_disease cerebrovascular --use-preset --run-id male_repro
```

For each package's details, expected key figures, and modifications, see the respective `backtest/README.md` /
`generational/README.md`.

## Data Sources

Attribution and terms of use for the third-party data bundled with both packages (Vital Statistics and Patient Survey / e-Stat,
National Cancer Registry / National Cancer Center, Standard Life Tables / The Institute of Actuaries of Japan) are
consolidated in `../DATA_SOURCES.md`.
