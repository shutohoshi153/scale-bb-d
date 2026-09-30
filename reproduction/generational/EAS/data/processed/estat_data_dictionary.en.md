[日本語](estat_data_dictionary.md) | **English**

# e-Stat API Data Dictionary

*English translation of [estat_data_dictionary.md](estat_data_dictionary.md) (as of 2026-08-05). If the versions disagree, the Japanese version is authoritative.*

This document describes the structure, code systems, and usage of all datasets retrieved from the e-Stat API for this study, "Applying the Scale BB Approach to Disease Incidence Rates."

- Last updated: 2026-04-22
- Source: e-Stat API v3.0 (<https://www.e-stat.go.jp/api/>)
- Related scripts: `scripts/estat_api_client.py` and others

---

## 1. Overview

### 1.1 Directory structure

```text
RowData/
  estat_api/                      # Raw JSON retrieved from the API (cache)
    getStatsList/                 # Statistical table search results
    getMetaInfo/                  # Metadata (not used in this retrieval)
    getStatsData/                 # Statistical data itself (per statsDataId)
    stats_list_summary_*.csv      # Table-list summaries for the 3 statistics (4,239 tables)
    priority_tables_patient_survey.csv  # Selection of the 30 tables used in this study
  estat_processed/                # Data converted to long CSV
    patient_survey/               # Patient Survey, 30 tables
      _manifest.csv
      Z{XX}__{statsDataId}.csv
    population/                   # Population Estimates (merged)
      pop_5yr_age_combined.csv    ← main file
      pop_5yr_age_series{A-G}__*.csv  (pre-merge original releases)
    vital_statistics/             # Vital Statistics, 6 tables
      5-{XX}_*__{statsDataId}.csv
```

### 1.2 Common column conventions

After conversion to long CSV, every file carries the following columns:

| Column | Type | Role |
|---|---|---|
| `<axis name>_code` | int/str | e-Stat internal code |
| `<axis name>` | str | Japanese label corresponding to the axis code |
| `unit` | str | Unit (e.g. `千人` [thousand persons], `人口10万対` [per 100,000 population], `人` [persons]) |
| `value_raw` | str/num | Raw `$` string from the API response |
| `value` | float | `value_raw` converted to a number (missing values are NaN) |

Axis names are taken from e-Stat's `CLASS_INF/@name` and differ slightly between tables (e.g. `年齢階級` / `年齢階級_004` / `年齢階級_006` [age group variants]). To unify them for downstream analysis, either extend `scripts/estat_stats_data_to_long.py` or rename on the reading side.

### 1.3 Handling of missing values and symbols

| Symbol | Meaning | Treatment in `value` |
|---|---|---|
| `-` | Not applicable | NaN |
| `…` | Outside survey scope | NaN |
| `※` | Recalculated with the finalized Census population | Converted to a number (annotation only) |
| Empty string | Missing | NaN |

---

## 2. Patient Survey (患者調査, statsCode=00450022)

### 2.1 List of included tables

| titleNo | statsDataId | Purpose | Rows | Main axes |
|---|---|---|---|---|
| **Z2-4** | 0004025884 | Patient counts, time series (1999-2023) | 675 | Sex x age x year |
| **Z3-2** | 0004025886 | Patient counts, time series (1996-2023, by disease) | 1,800 | Disease x inpatient-outpatient x year |
| **Z4-4** | 0004025890 | Consultation rates, time series (1999-2023) | 675 | Sex x age x year |
| **Z5-2** | 0004025892 | Consultation rates, time series (1996-2023, by disease) | 1,800 | Disease x inpatient-outpatient x year |
| Z2-1〜Z2-3 | - | Patient counts, time series (1955-1996) | Historical data | |
| Z3-1 | 0004025885 | Patient counts, time series (1979-1993, by disease) | 1,566 | |
| Z4-1〜Z4-3 | - | Consultation rates, time series (1955-1996) | Historical data | |
| Z5-1 | 0004025891 | Consultation rates, time series (1979-1993, by disease) | 1,566 | |
| **Z9** | 0004025899 | Patient counts (2023 cross-section) | 13,500 | Disease x age x sex x facility |
| Z10, Z11 | 0004025900/1 | Inpatient/outpatient patient counts | 13,500 / 40,500 | |
| Z12, Z13 | 0004025902/3 | Patient counts (major/intermediate disease classification) | 7,500-90,000 each | |
| Z14, Z15 | 0004025904/5 | Inpatient/outpatient (minor classification) | 50,250 | |
| **Z68** | 0004025961 | **Consultation rates, cross-section (5-year age x disease)** | 4,320 | Disease x age x sex |
| Z69 | 0004025962 | Inpatient consultation rates, cross-section | 4,320 | |
| Z70 | 0004025963 | Outpatient consultation rates, cross-section | 12,960 | x first visit/return visit |
| Z71 | 0004025964 | Consultation rates (major classification) | 32,040 | |
| **Z72** | 0004025965 | **Consultation rates (intermediate classification)** | 53,280 | |
| Z73 | 0004025966 | Consultation rates (minor classification) | 133,560 | Finest granularity |
| Z156-Z160 | 4026062-6 | Total patient counts | 4,000-24,000 each | Major/intermediate/minor/basic classification |

Bold marks the core tables for the Scale BB application.

### 2.2 Tabulated-item codes

| code | Tabulated item | Unit |
|---|---|---|
| 9 | 受療率（人口10万対） (consultation rate, per 100,000 population) | per 100,000 |
| 10 | 受療率（人口10万対）の年次推移 (consultation rate per 100,000, annual trend) | per 100,000 |
| 14 | 推計外来患者数 (estimated outpatients) | thousand persons |
| 16 | 推計患者数 (estimated patients) | thousand persons |
| 22 | 推計患者数の年次推移 (estimated patients, annual trend) | thousand persons |
| 29 | 推計入院患者数 (estimated inpatients) | thousand persons |
| 38 | 総患者数 (total patients) | thousand persons |
| 45 | 入院受療率（人口10万対） (inpatient consultation rate, per 100,000 population) | per 100,000 |

### 2.3 Disease classification axes (caution required)

Note that the Patient Survey's disease classification axes **do not include the Roman numeral (Ⅰ〜XXII) prefixes**:

```
API response:       '新生物＜腫瘍＞'
Legacy TXT sources: 'Ⅱ　新生物＜腫瘍＞'
```

Regrouped ("saikei" 再掲) items carry a leading U+3000 (full-width space):

```
'　（悪性新生物＜腫瘍＞）（再掲）'  # ← U+3000 prefix
```

Depending on the table, the axis appears as `傷病分類`, `傷病分類２`, `傷病分類_004`, `傷病大分類`, `傷病中分類`, `傷病小分類`, etc. (disease classification / major / intermediate / minor). Approximate granularity:

| Axis | Number of values | Example |
|---|---|---|
| 傷病分類/傷病分類２ (disease classification) | approx. 22-60 | Ⅰ〜XXII major classes + regrouped items |
| 傷病大分類 (major classification) | approx. 5-14 | Major classes only |
| 傷病中分類 (intermediate classification) | approx. 130-180 | Intermediate classes |
| 傷病小分類 (minor classification) | approx. 400-700 | Minor classes |
| 傷病基本分類 (basic classification) | approx. 5,000 | ICD-10 3-digit detail |

### 2.4 Age-group axis

Usually 22-25 groups in 5-year bands. Example code system:

```
1    総数 (total)
1001 0歳 (age 0)
1002 1-4歳 (ages 1-4)
1003 5-9歳 (ages 5-9)
...
1022 90歳以上 (ages 90 and over)
2001 (再掲) 65歳以上 (regrouped: ages 65 and over)
```

### 2.5 Time axes

| Axis name | Years covered |
|---|---|
| `年次30-40` (Z2-1, Z4-1) | 1955, 1960, 1965 (Showa 30, 35, 40) |
| `年次45-58` (Z2-2, Z4-2) | 1970, 1975, 1979, 1981, 1983 (Showa 45, 50, 54, 56, 58) |
| `年次59-H8` (Z2-3, Z4-3) | 1984, 1987, 1990, 1993, 1996 (Showa 59, 62, Heisei 2, 5, 8) |
| `年次11－29` (Z2-4, Z4-4) | 1999, 2002, 2005, 2008, 2011, 2014, 2017, 2020, 2023 (Heisei 11, 14, 17, 20, 23, 26, 29, Reiwa 2, Reiwa 5) |
| `年次54-H5` (Z3-1, Z5-1) | 1979, 1981, 1984, 1987, 1990, 1993 (Showa 54, 56, 59, 62, Heisei 2, 5) |
| **`年次8－29` (Z3-2, Z5-2)** | **1996, 1999, 2002, 2005, 2008, 2011, 2014, 2017, 2020, 2023 (Heisei 8, 11, 14, 17, 20, 23, 26, 29, Reiwa 2, Reiwa 5)** |

The core of this study is `年次8－29` (10 time points, 1996-2023).

### 2.6 Units and conversions

- Patient-count series: `千人` (thousand persons) → to recover the actual count, `value * 1000`
- Consultation-rate series: per 100,000 population → to recover the actual count, `value * population / 100000`

---

## 3. Population Estimates (人口推計, statsCode=00200524)

### 3.1 Combined file

**Main data: `RowData/estat_processed/population/pop_5yr_age_combined.csv`**

| Item | Content |
|---|---|
| Rows | 2,643 |
| Year coverage | 1980, 1985, 1990, 1995-2024 (**33 years; continuous for every year from 1995 onward**) |
| Age groups | 22 (+ 5 regrouped) = 27 |
| Sex | 男女計 (both sexes) / 男 (male) / 女 (female) |
| Region | Japan total only |
| Unit | thousand persons (population) or % (share) |

Merged from 7 releases (seriesA-G) with deduplication, preferring the most recent release. Merge logic is in `scripts/combine_population.py`.

### 3.2 Main columns

| Column | Example | Notes |
|---|---|---|
| `時間軸（年）` (time axis, year) | `2020年` | As of October 1 of each year |
| `年齢5歳階級` (5-year age group) | `0～4歳`, `65～69歳`, `（再掲）65歳以上` | 5-year bands + regrouped items |
| `男女別` (sex) | `男女計` (both sexes) / `男` (male) / `女` (female) | |
| `人口・割合` (population/share) | `人口` (population) / `割合` (share) | Both present in seriesB-G. Filter to `人口` for analysis |
| `value` | 127095 | In thousands of persons |
| `source` | `pop_5yr_age_seriesB__...` | Originating release |

### 3.3 Usage in analysis

```python
import pandas as pd

pop = pd.read_csv("RowData/estat_processed/population/pop_5yr_age_combined.csv")
# Keep population only (seriesB-G also contain shares)
pop = pop[(pop["人口・割合"].isna()) | (pop["人口・割合"] == "人口")]
# Both sexes only, exclude regrouped items
pop = pop[pop["男女別"] == "男女計"]
pop = pop[~pop["年齢5歳階級"].str.contains("再掲", na=False)]
# Align with the Patient Survey years
target_years = ["1996年", "1999年", "2002年", "2005年", "2008年",
                "2011年", "2014年", "2017年", "2020年", "2023年"]
pop = pop[pop["時間軸（年）"].isin(target_years)]
```

### 3.4 Known gaps

- **1981-1984, 1986-1989, and 1991-1994 are missing** (5-year intervals only)
  - Not needed: the Patient Survey runs on a 3-year cycle and mainly covers 1996 onward, so there is no impact
- All years 1996-2024 are retrieved continuously → denominators are available for all 10 Patient Survey time points

---

## 4. Vital Statistics (人口動態統計, statsCode=00450011)

### 4.1 List of included tables

| File | statsDataId | Rows | Main axes | Pri |
|---|---|---|---|---|
| `5-15_死因_性_5歳階級_年次_死亡数率__0003411659.csv` | 0003411659 | 57,375 | Cause of death x age x sex x year x deaths/rate | **1** |
| `5-25_悪性新生物_性_5歳階級_年次_死亡率__0003411669.csv` | 0003411669 | 8,800 | Cancer-specific x age x sex x year | 1 |
| `5-28_心疾患_性_年次_死亡数率__0003464100.csv` | 0003464100 | 2,728 | Heart disease x sex x year x 4 indicators | 1 |
| `5-27_脳血管_性_年次_死亡数率__0003464099.csv` | 0003464099 | 1,364 | Cerebrovascular x sex x year x 4 indicators | 1 |
| `5-12_死因_性_年次_死亡数率__0003411656.csv` | 0003411656 | 12,546 | Cause of death x sex x year (**from 1899**) | 2 |
| `5-26_悪性新生物_性_年次_年齢調整死亡率__0003464098.csv` | 0003464098 | 1,240 | Cancer subcategories x sex x year | 2 |

### 4.2 Cause-of-death annual-trend classification (used in 5-15 and 5-12)

| code | Name | Scale BB focus disease |
|---|---|---|
| `Hi00` | 総数 (total) | |
| `Hi01` | 結核 (tuberculosis) | |
| **`Hi02`** | **悪性新生物＜腫瘍＞ (malignant neoplasms)** | **Core of the study** |
| `Hi03` | 糖尿病 (diabetes mellitus) | |
| `Hi04` | 高血圧性疾患 (hypertensive diseases) | |
| **`Hi05`** | **心疾患（高血圧性を除く） (heart diseases, excluding hypertensive)** | **Core of the study** |
| **`Hi06`** | **脳血管疾患 (cerebrovascular diseases)** | **Core of the study** |
| `Hi07` | 肺炎 (pneumonia) | |
| `Hi08` | 慢性気管支炎及び肺気腫 (chronic bronchitis and emphysema) | |
| `Hi09` | 喘息 (asthma) | |
| `Hi10` | 胃潰瘍及び十二指腸潰瘍 (gastric and duodenal ulcer) | |
| `Hi11` | 肝疾患 (liver diseases) | |
| `Hi12` | 腎不全 (renal failure) | |
| `Hi13` | 老衰 (senility) | |
| `Hi14` | 不慮の事故 (accidents) | |
| `Hi15` | (再掲) 交通事故 (regrouped: transport accidents) | |
| `Hi16` | 自殺 (suicide) | |

### 4.3 Time axes

- 5-15 / 5-25: 25 years (1950, 1960, 1970, 1980, 1990, 2000, 2005, 2010, 2015, 2018-2024)
- 5-27 / 5-28: 31 years (1995-2024 continuous, plus a few extras)
- 5-12 / 5-26: **123 years / 31 years** (5-12 is an ultra-long series covering 1899-2024)

### 4.4 Tabulated items (5-27 and 5-28 contain several)

| code | Tabulated item | Unit |
|---|---|---|
| 10100 | 死亡数 (number of deaths) | persons |
| 10110 | 死亡率 (death rate) | per 100,000 population |
| 10120 | 年齢調整死亡率（平成27年モデル人口） (age-adjusted death rate, 2015 model population) | per 100,000 population |
| 10130 | 百分率 (percentage) | % |

---

## 5. Typical analysis recipes

### 5.1 Converting consultation rates to actual patient counts

```python
import pandas as pd

# Consultation rates (per 100,000 population; disease x year x inpatient/outpatient)
rates = pd.read_csv("RowData/estat_processed/patient_survey/Z5-2__0004025892.csv")
# Population (all-ages total)
pop = pd.read_csv("RowData/estat_processed/population/pop_5yr_age_combined.csv")
pop = pop[(pop["男女別"] == "男女計") & (pop["年齢5歳階級"] == "総数")]
pop = pop[(pop["人口・割合"].isna()) | (pop["人口・割合"] == "人口")]
pop["year"] = pop["時間軸（年）"].str.replace("年", "").astype(int)

# Japanese era year → Western year
era_map = {f"平成{n}年": 1988 + n for n in range(1, 32)}
era_map.update({f"令和{n}年": 2018 + n for n in range(1, 7)})
rates["year"] = rates["年次8－29"].map(era_map)

# Merge and convert to actual counts
merged = rates.merge(pop[["year", "value"]].rename(columns={"value": "pop_thousand"}),
                     on="year")
merged["患者数"] = merged["value"] * merged["pop_thousand"] * 1000 / 100000
```

### 5.2 Data for the Scale BB improvement-rate heatmap

```python
# Z4-4 (consultation rates, age x year) into an age x calendar-year matrix
rates = pd.read_csv("RowData/estat_processed/patient_survey/Z4-4__0004025890.csv")
rates = rates[rates["表側4－4－23表"].str.contains("総数・")]  # filter inpatient/outpatient separately
# Pivot → target matrix for the Scale BB heatmap
matrix = rates.pivot_table(index="表側4－4－23表", columns="年次11－29", values="value")
```

### 5.3 Cross-validation of death rates and patient counts

```python
# Disease: check the correlation between malignant neoplasms and cancer consultation rates
mortality = pd.read_csv("RowData/estat_processed/vital_statistics/5-15_死因_性_5歳階級_年次_死亡数率__0003411659.csv")
mortality = mortality[mortality["死因年次推移分類_code"] == "Hi02"]
# Match against the Patient Survey's 新生物＜腫瘍＞ (neoplasms) and compute correlation coefficients, etc.
```

---

## 6. Re-retrieval and update procedure

```powershell
# 1. Update the list of statistical tables (when new tables are published)
python scripts/fetch_estat_stats_list.py

# 2. Re-fetch the 30 Patient Survey tables
python scripts/bulk_fetch_patient_survey.py

# 3. Re-fetch and merge population data
python scripts/fetch_population_data.py
python scripts/combine_population.py

# 4. Re-fetch Vital Statistics
python scripts/fetch_vital_stats_data.py
```

All scripts are accelerated by caching from the second run onward (the same statsDataId is never re-downloaded). To force a re-download, pass `use_cache=False` when initializing the client.

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `statsDataId=[xxx]のデータは存在しません` (data does not exist) | Missing zero padding | Apply 10-digit `zfill(10)` |
| Category names do not match the TXT files | Roman numeral prefix / U+3000 differences | Reuse `normalize_category` from `scripts/verify_estat_full_comparison.py` |
| `value` is NaN | Raw data is `-` / `…` | `.dropna(subset=["value"])` |
| Garbled characters (Windows PowerShell) | `cp1252` codec | Set `$env:PYTHONIOENCODING = "utf-8"` |

---

## 8. References

- e-Stat API v3.0 official documentation: <https://www.e-stat.go.jp/api/api-info/e-stat-manual3-0>
- Patient Survey (MHLW): <https://www.mhlw.go.jp/toukei/list/10-20.html>
- Population Estimates (Statistics Bureau, MIC): <https://www.stat.go.jp/data/jinsui/>
- Vital Statistics (MHLW): <https://www.mhlw.go.jp/toukei/list/81-1a.html>
- Scale BB original report (SOA, 2012): `PDF/researchmortalityimprovebbreport.pdf`

---

## Appendix: Generated summary CSVs

| File | Purpose |
|---|---|
| `RowData/estat_api/stats_list_summary_all.csv` | Full list of 4,239 tables |
| `RowData/estat_api/priority_tables_patient_survey.csv` | Selection of the 30 priority tables |
| `RowData/estat_processed/patient_survey/_manifest.csv` | Retrieval results and row counts |
| `RowData/estat_processed/population/_manifest.csv` | Retrieval results for the 7 population releases |
| `RowData/estat_processed/vital_statistics/_manifest.csv` | Retrieval results for the 6 Vital Statistics tables |
| `RowData/estat_processed/Z5-2_api_vs_txt.csv` | Full-coverage match verification: API vs manual download |

---

## 9. Task A deliverables: integrated panels (`data/processed/`)

`scripts/build_disease_panel.py` generates 4 tidy panels (output in parallel as parquet and
CSV). As a rule, all downstream Scale BB tasks (B visualization / C model implementation)
take these as input.

### 9.1 Common normalization conventions

`scripts/panel_helpers.py` provides the following:

| Function | Role |
|---|---|
| `wareki_to_seireki` | 「平成8年 / 令和元年 / ２０２３年 / 1995年」→ 1996 / 2019 / 2023 / 1995 (Japanese era and full-width years to Western years) |
| `parse_age_label` | Age label (full-width digits, full-width tilde, regrouped, total) → `AgeBand(code, low, high, is_recap, is_total)` |
| `normalize_disease_label` | Strips Roman numeral/numeric prefixes; adopts the inner component of Z68's `大分類(内訳(再掲))` hierarchy; removes regrouped trailers; removes outer parentheses |
| `focus_disease_id` | Maps to the unified IDs for the 3 diseases + reference categories (table below) |
| `load_population` | Tidy load of `pop_5yr_age_combined.csv` (normalizes sex to `total/male/female`) |

Unified disease_id:

| disease_id | Scope | Notes |
|---|---|---|
| `cancer` | 悪性新生物＜腫瘍＞ (malignant neoplasms) | Common to Patient Survey / Vital Statistics (Hi02 / Hi022017) |
| `neoplasm_all` | 新生物＜腫瘍＞ (all neoplasms, major class incl. benign) | Patient Survey only |
| `cardiovascular_all` | 循環器系の疾患 (diseases of the circulatory system, major class) | Patient Survey only |
| `heart_disease` | 心疾患（高血圧性を除く） (heart diseases, excluding hypertensive) | Patient Survey (regrouped) / Vital Statistics (Hi05) |
| `ischemic_heart` | 虚血性心疾患（再掲） (ischaemic heart diseases, regrouped) | Patient Survey only |
| `cerebrovascular` | 脳血管疾患 (cerebrovascular diseases) | Patient Survey (regrouped) / Vital Statistics (Hi06) |
| `hypertensive` | 高血圧性疾患 (hypertensive diseases) | Patient Survey (regrouped) / Vital Statistics (Hi04 / Hi042017) |
| `total` | 総数 (total) | Vital Statistics (Hi00) only |

Age codes (`age_code`):

| Example | Meaning |
|---|---|
| `total` | All ages combined |
| `a00_04`, `a05_09`, ..., `a85_89`, `a90_94`, `a95_99` | 5-year age bands |
| `a90p`, `a100p` | Open-ended upper bands |
| `r65p`, `r75p`, `r15_64`, `r65_74` | Regrouped aggregates |
| `a00`, `a01_04` | Sub-5-year splits that exist only in Z68/Z72 |

### 9.2 `disease_period_panel.parquet` / `disease_panel.parquet`

- **Input**: `Z5-2__0004025892.csv` (consultation rates) + `Z3-2__0004025886.csv` (estimated patient counts) + total population
- **Rows**: 1,800
- **Primary key**: (`disease_norm`, `section`, `year`)
- **Year range**: 1996, 1999, 2002, 2005, 2008, 2011, 2014, 2017, 2020, 2023 (10 time points)
- **section**: `total` / `inpatient` / `outpatient`
- **Columns**:

| Column | Description |
|---|---|
| `disease_id` | Common ID for the 3 diseases (many rows are NaN; `disease_norm` is sometimes used instead) |
| `disease_norm` | Normalized Japanese disease name |
| `disease_is_recap` | Regrouped-item flag |
| `disease_raw` | Raw API response value |
| `section` | Ordered category: total < inpatient < outpatient |
| `year` | Western calendar year |
| `rate_per_100k` | Consultation rate (per 100,000 population) |
| `patients_thousand` | Estimated patient count from Z3-2 (thousand persons) |
| `patients_estimated_thousand` | rate x total population / 100,000 (in thousands) |
| `population_total_thousand` | Both-sexes total population as of October 1 of the year (thousand persons) |

**Validation**: `patients_estimated` and `patients_thousand` agree within ±0.2% (only 2011,
when some prefectures were excluded due to the Great East Japan Earthquake, differs by about 1.9%).

`disease_panel.parquet` is an alias of this file (the main deliverable specified in the handover prompt).

### 9.3 `age_period_panel.parquet`

- **Input**: `Z4-4__0004025890.csv` (all-disease combined consultation rates by age x sex x year) + population
- **Rows**: 675
- **Primary key**: (`section`, `sex`, `age_code`, `year`)
- **Year range**: 1999, 2002, 2005, 2008, 2011, 2014, 2017, 2020, 2023 (9 time points)
- **Granularity**: 20 five-year age bands + total / male / female + regrouped 65-and-over / 70-and-over
- **Columns**: `section, sex, age_code, age_label, age_low, age_high, age_is_recap,
  age_is_total, year, rate_per_100k, population_thousand, patients_estimated_thousand`

### 9.4 `age_disease_2023_panel.parquet`

- **Input**: `Z68__0004025961.csv` (major classification x 5-year age band x sex, 2023 cross-section) + 2023 population
- **Rows**: 4,320
- **Primary key**: (`disease_norm`, `sex`, `age_code`)
- **Limitations**:
  - `section` is `total` only (Z68 itself has no inpatient/outpatient split; see Z69 for inpatient / Z70 for outpatient detail)
  - `a00` (age 0) and `a01_04` (ages 1-4) have `population_thousand` = NaN because the population data only has an aggregate for ages 0-4
  - `a90p` (ages 90 and over) is NaN because the population side is split into `a90_94 + a95_99 + a100p`
  → In practice, the population join works for the 17 bands from ages 5-9 through 85-89 (consistent with the standard Scale BB grid)

### 9.5 `mortality_apc_panel.parquet`

- **Input**: `5-15_死因_性_5歳階級_年次_死亡数率__0003411659.csv` + population
- **Rows**: 7,899
- **Primary key**: (`disease_id`, `sex`, `age_code`, `year`)
- **Year range**: 1950, 1955, 1960, 1965, 1970, 1975, 1980, 1985, 1990, 1995, 2000, 2005, 2010,
  2013-2024 (25 time points)
- **Included disease_id**: `total`, `cancer`, `heart_disease`, `cerebrovascular`, `hypertensive`
- **Columns**: `disease_id, mortality_code, disease_raw, sex, age_code, age_label, age_low,
  age_high, age_is_recap, age_is_total, year, deaths, rate_per_100k, population_thousand`
- **Note**: With the 2017 ICD-10 revision, the internal codes for Hi02/Hi04 changed to `Hi022017` / `Hi042017`.
  `MORTALITY_CODE_TO_FOCUS` consolidates both lineages under the same ID.

### 9.6 How to run

```powershell
$env:PYTHONIOENCODING = "utf-8"
python scripts/build_disease_panel.py
```

Dependencies: `pandas`, `pyarrow`, `python-dotenv` (for data retrieval). Completes in about 2 seconds by default.
