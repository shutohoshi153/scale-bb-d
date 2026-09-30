[日本語](build_panel.md) | **English**

# Design Document — `build_panel.py` ([1] table 5-15 → disease panel, §3.1)

*English translation of [build_panel.md](build_panel.md) (as of 2026-08-06). If the versions disagree, the Japanese version is authoritative.*

> For the cross-script overview see [../SCRIPTS.en.md](../SCRIPTS.en.md); for the package as a whole see [../README.en.md](../README.en.md).

## 1. Role and position

Builds the tidy disease panel `data/disease_panel_mortality.csv`, read by every downstream script, from the raw CSV of Vital Statistics table 5-15 (死因_性_5歳階級_年次_死亡数率 — cause of death × sex × 5-year age group × year, deaths and rates, 1950–2024). It is the head of the pipeline (`run_all.sh` step [1]) and corresponds to paper §3.1 "Data and disease mapping".

## 2. Inputs and outputs

**Inputs**

| File | Content |
|---|---|
| `_paths.RAW_VITAL_CSV` | Raw CSV of e-Stat table ID 0003411659. Columns: `表章項目` (tabulated item: deaths/death rate), `性別` (sex), `年齢(5歳階級)` (5-year age group), `時間軸(年次)` (year), `死因年次推移分類_code` (cause-of-death trend classification code), `value`, etc. |

Note: `_paths.DISEASE_MAPPING` (`disease_estat_mapping.csv`) is referenced as a path, but the mapping actually used is hard-coded in the in-script `DISEASE_TO_HICODE` dict. The CSV serves as the documentation of the correspondence table for §3.1.2.

**Outputs**

| File | Content |
|---|---|
| `data/disease_panel_mortality.csv` | The panel itself. Columns: `disease_id`, `sex`, `year`, `age_low`, `rate_per_100k`, `deaths`. On the order of 8 diseases × 3 sexes × 75 years × 21 age groups = 12,600 rows |
| `data/panel_summary.csv` | For sanity checking: per disease × sex, the row count, year count, age-group count, and year range |

The first checkpoint of a correct reproduction is that this output matches the bundled reference file `data/prebuilt_disease_panel_mortality.csv`.

## 3. CLI arguments

None (run as `python build_panel.py`).

## 4. Processing flow (`main()`)

1. **Load & preprocess** — reads the raw CSV and strips the BOM (U+FEFF) from column names. Logs the row count and year range.
2. **Split by tabulated item** — separates rows with `表章項目 == "死亡数"` (deaths) from `== "死亡率"` (rate, per 100,000 population).
3. **Column normalization** (applied to both rate and deaths)
   - `性別` → `sex`: {総数→total, 男→male, 女→female}
   - `年齢(5歳階級)` → `age_low`: from label to lower-bound age (0, 5, …, 100) via the `AGE_LABEL_TO_LOW` dict. "総数" (all ages) and "不詳" (unknown) map to `None` and are removed by the later `dropna`. The **label strings** are used as keys rather than codes, for robustness across encodings.
   - `時間軸(年次)` → `year`: strips "年" and casts to int.
4. **Disease mapping** — maps `死因年次推移分類_code` (Hi codes) to `disease_id` via the inverse of `DISEASE_TO_HICODE`. Rows with unmapped cause/sex/age are dropped by `dropna`.
5. **Join & write** — left-joins the deaths side (`deaths`) onto the rate side (`rate_per_100k`) on the key `(disease_id, sex, year, age_low)`, sorts by the key, and writes the CSV. The per-disease/sex summary table is written as well.

## 5. Constant specifications

**`DISEASE_TO_HICODE`** — disease slug → cause-of-death trend classification code:

| disease_id | Hi code | Notes |
|---|---|---|
| cancer | `Hi022017` | Because of the 2017 classification revision, the full 1950–2024 period is stored under the 2017-revision code |
| diabetes | `Hi03` | |
| hypertensive | `Hi042017` | 2017-revision code, same as cancer |
| heart_disease | `Hi05` | Heart disease excluding hypertensive; slug shared by the paper and both reproduction packages |
| cerebrovascular | `Hi06` | |
| liver | `Hi11` | |
| kidney | `Hi12` | Kidney failure (closest available category in table 5-15) |
| total | `Hi00` | All causes |

Ischemic heart disease (heart_ischemic) does not exist in the trend classification (only in the simple classification, table 5-28, which lacks 5-year age groups) and is therefore excluded.

**`AGE_LABEL_TO_LOW`** — dict from 5-year age-group label to lower-bound age ("0～4歳"→0 … "100歳以上"→100; "総数"/"不詳" → `None`).

## 6. Implementation notes

- Death rates are used **as published** in table 5-15 (per 100,000 population); this script performs no recomputation or adjustment of rates.
- The deaths join uses `how="left"` (the rate side is primary); rows with missing deaths keep their rate.
- Uniqueness of output rows relies on the data quality on the e-Stat side (the script only filters and joins; it does not pivot).
