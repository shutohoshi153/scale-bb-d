[日本語](apc_predicted_rate_tables_by_sex_20260423.md) | **English**

# APC Version: Sex-Specific Expected Disease Incidence Rate Tables — Production Report

*English translation of [apc_predicted_rate_tables_by_sex_20260423.md](apc_predicted_rate_tables_by_sex_20260423.md) (as of 2026-08-05). If the versions disagree, the Japanese version is authoritative.*

> **Note (2026-07-16, terminology supplement following the paper's retitling):** The
> "expected disease incidence rate tables" in this report are in substance rate tables computed
> from **cause-specific mortality rates** as input (per 100,000 population, derived from
> `mortality_apc_panel`) (see §2 "Input Data"). In the paper (retitled 2026-07-15:
> *from All-Cause to Cause-Specific Mortality*), these cause-specific mortality rates are used
> at two levels: **(i) as a proxy for disease incidence rates in medical insurance**, and
> **(ii) as the direct subject (direct assumption) of specified-disease death benefit coverage**.
> The term "incidence rate" in the title and body is product-side nomenclature; the inputs and
> computations are consistently cause-specific mortality rates (the ScaleBB algorithm is agnostic
> to the meaning of its input, so the numbers are unchanged).

- **Date produced**: 2026-04-23
- **Target model**: Scale BB APC (Age-Period-Cohort) extension
- **Target diseases**: cancer / heart_disease / cerebrovascular (the three leading causes of death)
- **Target sexes**: male / female (fitted separately)
- **Issue years (issue_year)**: 2024 / 2025 / 2026 / 2027 / 2028
- **Age at issue (issue_age)**: 40
- **Age range**: 40–85 (single ages, log-linear interpolation from 5-year bins)
- **Final projection year**: 2100 (covers all ages reachable by a policyholder entering at age 40)

---

## 1. Purpose

This report summarizes the process and results of integrating the **APC-extended
Scale BB** model implemented in `scripts/scale_bb_apc_model.py` into the EAS
pipeline and generating **sex-specific** expected disease incidence rate tables
(1D `[age] per (sex, disease, issue_year)`).

The motivation for adopting APC, as laid out in the earlier report
[`methodology_apc_extension_20260422.md`](methodology_apc_extension_20260422.md),
comes down to the following two points.

1. **Identification of cohort effects**: Separate morbidity tendencies driven by
   birth year (e.g., smoking habits, living environment) from the Period effect,
   and reflect differences in "at what age one was exposed" before and after
   the COVID-19 pandemic.
2. **Maintaining downstream operational compatibility**: The APC extension makes
   the model itself 3D (sex × age × year), but through Generational Projection
   **what is distributed downstream remains a 1D table in the conventional
   `[sex, age]` format**.

---

## 2. Input Data

| Item | Content |
|---|---|
| Source data table | `data/processed/mortality_apc_panel.parquet` |
| Source | e-Stat Vital Statistics (cause-specific mortality rates) |
| Age grouping | **5-year classes** (40–44, 45–49, …, 85–89) — 10 classes in total |
| Calendar years | 1950–2024 (5-year steps, 25 years in total) |
| Sex | total / male / female |
| Unit | Deaths per 100,000 population |

> **Note**: The 5-year age classes are a constraint of the source data. The
> assumed-rate table side interpolates to single ages (Section 5 of this report).

---

## 3. Full Pipeline Diagram

```text
┌──────────────────────────────────────────────────────────────────────┐
│  mortality_apc_panel  (sex × age[5y] × year[5y])                      │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │ ① scalebb-apc-fit
                                 │   (2D WH smoothing + diagonal penalty + COVID dummy)
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  scalebb_improvement  +  scalebb_cohort_effect                        │
│    rate_smoothed / improvement_smoothed             γ(cohort)         │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │ ② scalebb-apc-project
                                 │   (improvement rate × L blend + cohort extrapolation)
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  scalebb_projection  (sex × age[5y] × year 1950-2100)                 │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │ ③ scalebb-gen-table --interpolate-age
                                 │   (Generational Projection +
                                 │    log-linear single-age interpolation)
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  predicted_rate_generational  (sex × disease × issue_year × age[1y])  │
│  + CSV per (disease, sex, issue_year)                                 │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 4. Production Commands (Full Reproduction)

### 4.1 Configuration preset (see config.yaml)

| Parameter | Value | Meaning |
|---|---|---|
| `lam_row` / `lam_col` / `lam_cohort` | 40.0 / 40.0 / 40.0 | WH smoothing penalties (age / period / cohort) |
| `long_term_rate` | 0.01 | Long-term improvement rate L (1% per the original source) |
| `convergence_year` | 2035 | Year by which the improvement rate converges to L |
| `horizon_year` | 2100 | Final projection year |
| `covid_mode` | `dummy` | Separate the COVID years (2020-2022) as a period shift |
| `covid_years` | 2020, 2021, 2022 | COVID target years |
| `age_min` / `age_max` | 40 / 85 | Target age range |
| `interpolate_age` | true | 5-year bins → single-age interpolation (log_linear) |

From the CLI, `--use-preset` applies all of the above at once (merging
`scalebb_presets.defaults` + `diseases.<name>` + `sex.<male|female>` from
`config.yaml` in that order; explicitly specifying options such as `--lam-row`
gives CLI arguments precedence).

### 4.2 Male pipeline

```bash
# Add src to PYTHONPATH (run from directly inside EAS)
$env:PYTHONPATH = "src"; $env:PYTHONIOENCODING = "utf-8"

# ① APC fit (male, 3 diseases)
python -m experience_rate scalebb-apc-fit `
  --source mortality `
  --sex male `
  --disease cancer heart_disease cerebrovascular `
  --use-preset `
  --run-id male_apc02

# ② APC project (project through 1950-2100)
python -m experience_rate scalebb-apc-project `
  --fit ../data/processed/scalebb_apc_fit_male.parquet `
  --use-preset `
  --run-id male_apc02_proj

# ③ Generational Table (issue years 2024-2028, issue_age=40, single-age interpolation)
python -m experience_rate scalebb-gen-table `
  --run-id male_apc02_proj `
  --use-preset `
  --output-dir ../data/processed/predicted_rate_apc
```

### 4.3 Female pipeline

```bash
python -m experience_rate scalebb-apc-fit `
  --source mortality --sex female `
  --disease cancer heart_disease cerebrovascular `
  --use-preset --run-id female_apc01

python -m experience_rate scalebb-apc-project `
  --fit ../data/processed/scalebb_apc_fit_female.parquet `
  --use-preset --run-id female_apc01_proj

python -m experience_rate scalebb-gen-table `
  --run-id female_apc01_proj --use-preset `
  --output-dir ../data/processed/predicted_rate_apc
```

### 4.4 AP (conventional) pipeline for comparison

For comparison against APC, the conventional AP model
(`scripts/scale_bb_disease.py`) was run on the same mortality_apc_panel with
the same parameters:

```bash
python -m experience_rate scalebb-fit --source mortality --sex male --age-min 40 --age-max 89 --run-id male01
python -m experience_rate scalebb-project --fit ../data/processed/scalebb_fit.parquet --run-id male01p --horizon 2100
python -m experience_rate scalebb-gen-table --run-id male01p --use-preset

python -m experience_rate scalebb-fit --source mortality --sex female --age-min 40 --age-max 89 --run-id female01
python -m experience_rate scalebb-project --fit ../data/processed/scalebb_fit.parquet --run-id female01p --horizon 2100
python -m experience_rate scalebb-gen-table --run-id female01p --use-preset
```

---

## 5. Single-Age Interpolation (5-Year Bins → Single Ages)

Because mortality_apc_panel uses 5-year age classes, it cannot be used as-is for
the `[sex, age]` assumed rate tables (contract unit: single ages).
`scalebb_gen.interpolate_projection_ages()` provides the following three methods.

| method | Definition | Recommended use |
|---|---|---|
| `log_linear` (default) | Interpolate `log(rate)` linearly in age → `exp` | Disease incidence rates (exponential growth with age) |
| `linear` | Interpolate `rate` linearly in age | Cases where the rate changes roughly linearly |
| `log_pchip` | Monotone PCHIP interpolation of `log(rate)` | When the monotonicity of the 5-year grid must be strictly preserved |

Interpolation illustration (male cancer, issue_year=2026, issue_age=40):

| age | 5-year bin (source) | log-linear interpolation (output) |
|---:|---:|---:|
| 40 | 20.11 | **20.11** (match) |
| 41 |  —   | 22.17 |
| 42 |  —   | 24.49 |
| 43 |  —   | 27.12 |
| 44 |  —   | 30.10 |
| 45 | 33.49 | **33.49** (match) |
| 50 | 58.83 | **58.83** |
| ... | ... | ... |
| 85 | 2218.26 | **2218.26** |

Known points match exactly; intermediate ages reproduce exponential growth of
roughly 12–13% per year of age.

---

## 6. Results Summary

### 6.1 DB row counts

| run_id | kind | sex | improvement | projection | cohort_effect | generational |
|---|---|---|---:|---:|---:|---:|
| `male_apc02`       | fit | male    | 750 |  0  | **210** |  0  |
| `male_apc02_proj`  | projection | male | 0 | 4,530 | 0 | **690** |
| `female_apc01`     | fit | female  | 750 |  0  | **210** |  0  |
| `female_apc01_proj`| projection | female | 0 | 4,530 | 0 | **690** |
| `male01` / `male01p`     | AP reference | male   | 750 / 4,530 | — | — / **690** |
| `female01` / `female01p` | AP reference | female | 750 / 4,530 | — | — / **690** |

- improvement: 3 diseases × 10 ages × 25 years = 750 rows
- projection: 3 × 10 × 151 years = 4,530 rows
- cohort_effect: 3 × 70 cohorts (1865–1984) = 210 rows
- generational: 3 × 5 issue_years × 46 ages = 690 rows (per one sex, male or female)

### 6.2 Assumed incidence rates (issue year 2026, issue_age=40, after single-age interpolation)

**Comparison of 3 diseases × both sexes (per 100,000 population, selected key ages only):**

| age | cancer M | cancer F | heart M | heart F | cerebro M | cerebro F |
|---:|---:|---:|---:|---:|---:|---:|
| 40 |   20.1 |   33.3 |   15.8 |    3.8 |   10.3 |    4.5 |
| 50 |   58.8 |   70.0 |   39.3 |   10.1 |   22.7 |    9.7 |
| 60 |  184.9 |  147.2 |   96.2 |   25.6 |   47.4 |   19.5 |
| 70 |  542.4 |  296.4 |  226.9 |   69.5 |  101.6 |   42.1 |
| 80 | 1405.9 |  575.4 |  537.8 |  214.5 |  228.3 |  103.7 |
| 85 | 2218.3 |  799.9 |  838.2 |  388.6 |  345.7 |  167.4 |

> **Reading the table**:
> - Cancer: female > male in the 40s–50s (young-age peak of breast and
>   cervical cancer); reverses to male > female from the 60s onward.
> - Heart disease and cerebrovascular disease: males tend to be roughly 2–4
>   times higher at all ages.

### 6.3 APC vs. AP difference (male cancer, issue_year=2026)

| age | APC | AP (conventional) | Difference |
|---:|---:|---:|---:|
| 40 |   20.1 |   20.9 | **−3.8%** |
| 45 |   33.5 |   35.2 | −4.8% |
| 50 |   58.8 |   60.7 | −3.1% |
| 55 |  104.6 |  104.5 | +0.1% |
| 60 |  184.9 |  177.7 | +4.1% |
| 65 |  321.3 |  296.9 | +8.2% |
| 70 |  542.4 |  485.7 | +11.7% |
| 75 |  884.6 |  778.0 | +13.7% |
| 80 | 1405.9 | 1228.5 | **+14.4%** |
| 85 | 2218.3 | 1926.2 | **+15.2%** |

**Interpretation**:

- Younger ages (40s): APC is slightly lower (reflecting the declining relative
  rates of recent cohorts)
- Older ages (70–85): **APC is 12–15% higher than AP** — modern cohorts (born
  1950–1970) carry higher smoking-history and lifestyle risk than prewar
  generations, shifting γ(c) positive. In AP this was absorbed into the period
  effect, whereas APC explicitly separates it out as γ.

### 6.4 Cohort effect γ(cohort) excerpt (cancer)

| cohort (birth year) | male γ | female γ | Remarks |
|---:|---:|---:|---|
| 1870 | −1.23 | −0.89 | Early Meiji era (below baseline level) |
| 1890 | −0.28 | −0.15 | Late Meiji era |
| 1910 | +0.18 | +0.16 | Taisho era (pre-peak) |
| **1930** | **+0.27** | **+0.16** | **Highest-cancer-risk cohort** |
| 1950 | +0.07 | −0.00 | Baby-boom (dankai) generation, decline begins |
| 1970 | −0.39 | −0.25 | Anti-smoking movement, lifestyle improvements |
| 1980 | −0.73 | −0.40 | Low-risk cohort |
| 1984 | −0.77 | −0.40 | Observation endpoint |

The amplitude of γ is larger for males than for females (the rise from the
prewar generations to the 1930 birth cohort is pronounced), peaking with the
1930 cohort and declining to −0.77 (≒ exp(−0.77) = 46% relative) for the 1984
cohort. This is consistent with the decline in smoking rates and in stomach
cancer among Japanese men.

---

## 7. Output File List

### 7.1 Intermediate artifacts (parquet/CSV for DB input)

```text
data/processed/
├── scalebb_apc_fit_male.parquet        (750 rows; rate_smoothed etc.)
├── scalebb_apc_fit_male.csv
├── scalebb_apc_fit_male.cohort.csv     (210 rows; γ(cohort))
├── scalebb_apc_fit_male.meta.json      (APC config)
├── scalebb_apc_fit_female.parquet
├── scalebb_apc_fit_female.cohort.csv
├── scalebb_apc_projection_male.parquet   (4,530 rows; rate_projected 1950-2100)
├── scalebb_apc_projection_male.csv
└── scalebb_apc_projection_female.parquet
```

### 7.2 Distribution assumed incidence rate tables (APC)

Location: `data/processed/predicted_rate_apc/`

| File name pattern | Rows | Content |
|---|---:|---|
| `predicted_rate_cancer_male_issue{YYYY}_ia40.csv`         | 46 | Male, cancer, each issue year (ages 40–85) |
| `predicted_rate_cancer_female_issue{YYYY}_ia40.csv`       | 46 | Female, cancer |
| `predicted_rate_heart_disease_male_issue{YYYY}_ia40.csv`  | 46 | Male, heart disease |
| `predicted_rate_heart_disease_female_issue{YYYY}_ia40.csv`| 46 | Female, heart disease |
| `predicted_rate_cerebrovascular_male_issue{YYYY}_ia40.csv`| 46 | Male, cerebrovascular |
| `predicted_rate_cerebrovascular_female_issue{YYYY}_ia40.csv`| 46 | Female, cerebrovascular |

Each issue year {2024,2025,2026,2027,2028} × 3 diseases × 2 sexes = **30 files** +
2 master CSVs (male_apc, female_a). Each file contains

```csv
age,rate_per_100k
40,20.11460760300782
41,22.16528217233873
42,24.487563508215846
...
85,2218.2630148017143
```

2 columns × 46 rows. The future projection year can be recovered via
`year_lookup = issue_year + (age − issue_age)`.

### 7.3 DB tables

```sql
-- Added by the APC extension
scalebb_cohort_effect
  run_id TEXT, disease_id TEXT, sex TEXT, section TEXT,
  cohort INTEGER, gamma REAL, is_observed INTEGER
  PRIMARY KEY (run_id, disease_id, sex, section, cohort)

-- Existing (shared with AP)
predicted_rate_generational
  run_id, disease_id, sex, section,
  issue_year, issue_age, age, rate_per_100k, year_lookup
```

---

## 8. Operational Guidelines

### 8.1 Recommended preset application policy

Using `scalebb_presets` in `config.yaml` automates the following.

- Treatment of the COVID period (2020-2022): **`dummy` mode** (separated as a
  β shift)
- Smoothing parameter λ: 40.0 (following the original source as a value that
  ensures smoothness of the ICP (incidence curve plot))
- `lam_cohort` for cerebrovascular disease is lowered to 20.0 — the rapid
  decline in mortality since the prewar generations produces strong curvature
  in the cohort direction, requiring a weaker penalty

### 8.2 Update frequency

| Update timing | Target | Method |
|---|---|---|
| Annually (after e-Stat release) | Extend mortality_apc_panel by +1 year | Re-run `build_disease_panel.py`, then APC fit |
| Annually | Re-estimate γ(c) | Re-run `scalebb-apc-fit` |
| Annually | Reissue assumed rate tables | `scalebb-apc-project` + `scalebb-gen-table` |
| Per issue year | Dedicated tables per policy issue year | Generate additionally with `--issue-years <yr>` |

### 8.3 Caveats on single-age interpolation

- `log_linear` is smooth, but if the disease profile has a kink within a 5-year
  bin (e.g., the female cancer breast-cancer peak at 45-55), it may deviate
  from the true values
- For contract design, validation is needed to confirm that the average error
  within each 5-year bundle is within tolerance
- If e-Stat publishes single-age data in the future, it can be used directly
  with `--no-interpolate-age`

---

## 9. Related Documents

- [APC extension methodology](methodology_apc_extension_20260422.md) — Mathematical formulation and identifiability
- [Comparative validation against the traditional method](validation_scalebb_vs_traditional_20260422.md) — AP version vs. traditional methods
- `EAS/README.md` — General CLI reference
- `EAS/docs/Scale_BB機能.md` — DB schema details

---

## Appendix A: Execution Log (Summary)

```
[apc-fit] disease=cancer sex=male section=total n_age=10 n_year=25
         year_range=1950-2024 covid_mode=dummy
[apc-fit] disease=heart_disease sex=male section=total ...
[apc-fit] disease=cerebrovascular sex=male section=total ...
[apc-load] scalebb_improvement=750 rows, scalebb_cohort_effect=210 rows
           (run_id=male_apc02)

[apc-project] disease=cancer sex=male project_years=1950-2100
[apc-load] scalebb_projection=4530 rows (run_id=male_apc02_proj)

[interpolate] method=log_linear rows: 4530 → 20286
[scalebb-gen-table] rows_loaded = 690   files_written = 15
                    interpolate_age = True (log_linear)
```

(The female side follows the identical pattern.)

---

## Appendix B: Age-20-Start Extended Version (Addendum, 2026-04-23)

### B.1 Background and motivation

While the previous target was ages 40 and above, we extended the starting age of
the analysis to **20**, anticipating application to **medical insurance products
for younger policyholders and educational endowment insurance**. mortality_apc_panel
is continuous from ages 20-24 (Section 2), so we take in 4 additional classes
(20-24, 25-29, 30-34, 35-39).

### B.2 Configuration changes (`config.yaml`)

```yaml
scalebb_presets:
  defaults:
    age_min: 20           # 40 → 20
    age_max: 85
    lam_col: 60.0         # 40.0 → 60.0 (strengthened to suppress young-age noise)
  generational:
    issue_age: 20         # 40 → 20
    age_min: 20           # 40 → 20
    age_max: 85
```

`lam_col` was strengthened from 40→60 because mortality rates in the 20s-30s
are small in absolute terms (e.g., male cerebrovascular at ages 20-24 ≒
0.45 / 100k), so year-to-year statistical fluctuation is relatively large
(a Poisson-like small-sample effect).

### B.3 Execution (both sexes × 3 diseases)

```bash
$env:PYTHONPATH = "src"; $env:PYTHONIOENCODING = "utf-8"

# Male
python -m experience_rate scalebb-apc-fit --sex male --use-preset --run-id male_apc03_age20
python -m experience_rate scalebb-apc-project --fit ../data/processed/scalebb_apc_fit_male.parquet `
  --use-preset --run-id male_apc03_age20_proj
python -m experience_rate scalebb-gen-table --run-id male_apc03_age20_proj --use-preset `
  --output-dir ../data/processed/predicted_rate_apc_age20

# Female
python -m experience_rate scalebb-apc-fit --sex female --use-preset --run-id female_apc02_age20
python -m experience_rate scalebb-apc-project --fit ../data/processed/scalebb_apc_fit_female.parquet `
  --use-preset --run-id female_apc02_age20_proj
python -m experience_rate scalebb-gen-table --run-id female_apc02_age20_proj --use-preset `
  --output-dir ../data/processed/predicted_rate_apc_age20
```

### B.4 DB row counts (after the extension)

| run_id | kind | n_age | improvement | projection | cohort_effect | generational |
|---|---|---:|---:|---:|---:|---:|
| `male_apc03_age20`       | fit | **14** | 1,050 | — | **270** | — |
| `male_apc03_age20_proj`  | projection | 14 | — | 6,342 | — | **990** |
| `female_apc02_age20`     | fit | **14** | 1,050 | — | **270** | — |
| `female_apc02_age20_proj`| projection | 14 | — | 6,342 | — | **990** |

- n_age: 10→**14** (14 classes, 20-24 ~ 85-89)
- cohort_effect: 210→**270** (young cohorts born 1985-2004 added)
- generational: 690→**990** (5 issue years × 3 diseases × **66 ages** = 20-85)

### B.5 Young-age assumed rates (APC, issue year 2026, **entry at age 20**)

#### Both sexes × 3 diseases × key young ages (per 100,000 population)

| age | cancer M | cancer F | heart M | heart F | cerebro M | cerebro F |
|---:|---:|---:|---:|---:|---:|---:|
| 20 |  2.38 |  2.31 | 1.66 | 0.76 | 0.45 | 0.30 |
| 25 |  3.80 |  3.93 | 2.58 | 1.19 | 0.81 | 0.48 |
| 30 |  6.02 |  6.91 | 4.19 | 1.81 | 1.62 | 0.92 |
| 35 |  9.66 | 12.28 | 6.86 | 2.59 | 3.25 | 1.68 |
| 40 | 15.84 | 21.60 |11.25 | 3.73 | 6.28 | 2.84 |

**Observations**:

- **Ages 20-24**: Cancer is roughly the same level for both sexes (~2.3 / 100k); cerebrovascular is about 1.5× higher for males than females
- **Ages 25-35**: **Female cancer exceeds male** (young-age peak of breast and cervical cancer)
- **Reversal around age 35**: From age 40 onward, males are higher (consistent with the earlier findings)

### B.6 Young-cohort γ(c) effects — new findings

For the 4 cohorts born 1985-2004, APC newly estimated γ.

| cohort | disease | male γ | female γ | Interpretation |
|---:|---|---:|---:|---|
| 1990 | cancer | −0.30 | −0.27 | Similarly low risk |
| 2004 | cancer | −0.29 | **−0.61** | **Continued decline for young females** |
| 1990 | cerebrovascular | +0.16 | +0.23 | Young cerebrovascular somewhat elevated |
| 2004 | cerebrovascular | +0.12 | **+0.41** | **Rising cerebrovascular risk in young females** |
| 1990 | heart_disease | −0.11 | −0.22 | Declining for both sexes |
| 2004 | heart_disease | −0.31 | +0.04 | Continued decline for males; **reversal for females** |

**Points of note**:

1. **Continued decline in young-female cancer γ** (−0.27 → −0.61, equivalent to
   exp⁻¹ = 45%): suggests contributions from screening uptake, the cervical
   cancer (HPV) vaccine, and declining smoking rates
2. **Rising cerebrovascular γ in young females** (+0.23 → +0.41): more recent
   generations show increasing relative risk — hypothesized drivers include
   rising obesity, physical inactivity, and hypertension at younger ages
3. **Young-female heart disease γ reverses in the 2004 cohort** (−0.22 → +0.04):
   the long-standing downward trend may have halted in the youngest generation
   (the stability of the statistical identification requires verification)

These are generational effects that were **unobservable in the previous
age-40-start APC**; incorporating young-cohort information yielded new insights.

### B.7 Change in `year_lookup` for the Generational Projection

**Important**: Changing `issue_age=40→20` changes `year_lookup` even for the
same `age=40`, so the values change (this is not a bug).

| issue_age | year_lookup at age=40 (issue year 2026) | female cancer value |
|---:|---|---:|
| 40 (old) | 2026 (the contract year itself) | 33.3 |
| **20 (new)** | **2046** (when an entrant at age 20 reaches age 40) | **21.6** |

year_lookup 20 years in the future = the accumulation of the long-term
improvement rate L=1%/year, `(1 − 0.01)^20 ≒ 0.82`, ≒ an 18% downward shift.
On top of this comes the effect of re-smoothing the age profile in the APC
projection.

### B.8 Outputs (age20 version)

- `data/processed/predicted_rate_apc_age20/` - 30 CSVs × 66 ages
- `data/processed/scalebb_apc_fit_male.parquet` - 1,050 rows
- `data/processed/scalebb_apc_projection_male.parquet` - 6,342 rows
- `data/processed/scalebb_apc_fit_male.cohort.csv` - 270 rows (70→90 cohorts)
- female has the identical structure

### B.9 Remaining issues

1. **Small-sample stability**: Mortality at ages 20-24 has large Poisson
   variability. We raised `lam_col=60` for numerical stabilization, but the
   **year-to-year observational variability at ages 20-29** should be
   cross-checked with a separate ICI (inter-cohort interval)-type metric
2. **Insufficient number of young cohorts**: γ for the 2004 birth cohort sits at
   the end of the observation period (reaching age 20 in 2024), so effectively
   only one year of data is available. Incorporating 2025-2029 data will
   stabilize the γ(c) estimates
3. **Comparison with disease incidence rates**: Using
   `EAS/data/RowData/cancer_incidenceNCR(2016-2023).xls` (cancer registry data)
   in parallel, a separate extension is being considered to quantify the gap in
   assumed rates between the **mortality basis** and the **incidence basis**
