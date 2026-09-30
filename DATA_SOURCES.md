# Data Sources

This page lists the sources and terms of use of the third-party data bundled in this repository.
The repository's own license (`LICENSE`) does not extend to the third-party data listed here.
Use of each dataset is governed by the terms set by its respective provider.

The third-party data bundled in this repository is credited below.
The repository's own license does not extend to these datasets; each remains
subject to the terms of its provider.

---

## 1. National Cancer Registry — cancer incidence counts and rates (National Cancer Center Japan)

**Japanese citation (和文出典表記):**

> 国立がん研究センターがん情報サービス「がん統計」（全国がん登録）

**English citation:**

> Cancer Statistics. Cancer Information Service, National Cancer Center, Japan
> (National Cancer Registry, Ministry of Health, Labour and Welfare)

| Item | Details |
| --- | --- |
| File | `reproduction/generational/EAS/data/RowData/cancer_incidenceNCR(2016-2023).xls` |
| Status | **Original file as downloaded** from the provider (unmodified) |
| Use | A-tier benchmark as the true incidence rate (§3.3; generational README §1) |
| Terms of use | Reproduction permitted with attribution. No prior application required. Use is conditional on keeping the original content unmodified |
| Provider's terms page | https://ganjoho.jp/aboutus/attention/copyright.html |

**Derived data:** `reproduction/generational/EAS/scripts/build_cancer_registry_panel.py`
in this package converts the original file above into a panel by age group and sex,
producing `data/processed/incidence_panel.csv` (rows with `rate_type='registry'`).
This conversion and the resulting figures are the work of the authors of this study,
and the National Cancer Center bears no responsibility for their content. For the
original figures, refer to the `.xls` file above.

*Derived data:* rows with `rate_type='registry'` in `data/processed/incidence_panel.csv`
are produced by the authors' script from the original file above. The National Cancer
Center is not responsible for the processed figures.

---

## 2. Standard Life Tables (The Institute of Actuaries of Japan) — not bundled

The optional input check `reproduction/generational/EAS/scripts/analyze_standard_life_table.py`
(generational README §4.3) compares the input mortality with the Standard Life Tables
1996 / 2007 / 2018 published by the Institute of Actuaries of Japan. The workbook it reads
(`data/lifetable/seimeihyo960718.xlsx`) is **not bundled** in this repository, because terms
for its redistribution have not been confirmed. The check is not part of any result of the
paper, and the assumed-rate tables do not depend on it.

---

## 3. Vital Statistics (Ministry of Health, Labour and Welfare / e-Stat)

**Citation (出典表記):**

> 厚生労働省「人口動態調査」（政府統計の総合窓口 e-Stat）
> (Vital Statistics (人口動態調査), Ministry of Health, Labour and Welfare, via e-Stat (政府統計の総合窓口))

| Item | Details |
| --- | --- |
| File | `reproduction/backtest/data/raw/5-15_死因_性_5歳階級_年次_死亡数率__0003411659.csv` (statistical table ID 0003411659: deaths and death rates by cause of death, sex, and 5-year age group, annual, 1950–2024) |
| Derived files | `reproduction/backtest/data/prebuilt_disease_panel_mortality.csv`, `reproduction/generational/EAS/data/processed/mortality_apc_panel.*`, and the `rate_type='mortality'` rows of `incidence_panel.csv` |
| Use | Primary input of this study (cause-specific mortality rates). The entire pipeline of §3.1–§3.4 |
| Terms of use | Under the Government of Japan Standard Terms of Use (version 2.0), reproduction, adaptation, and commercial use are permitted with attribution |

## 4. Patient Survey (Ministry of Health, Labour and Welfare / e-Stat)

**Citation (出典表記):**

> 厚生労働省「患者調査」（政府統計の総合窓口 e-Stat）
> (Patient Survey (患者調査), Ministry of Health, Labour and Welfare, via e-Stat (政府統計の総合窓口))

| Item | Details |
| --- | --- |
| Derived files | The `rate_type='initial_visit'` / `'discharge'` rows of `reproduction/generational/EAS/data/processed/incidence_panel.csv`, and `los_panel.csv` (each row retains the source statistical table ID in the `source_table` column) |
| Use | Incidence-rate proxies based on consultation rates and average length of stay (B/C-tier reference series) |
| Terms of use | Under the Government of Japan Standard Terms of Use (version 2.0), reproduction, adaptation, and commercial use are permitted with attribution |
| Note | To reduce repository size, the raw e-Stat data itself is not bundled (only the constructed panels are included) |

---

## 5. Yield curve creation tool (Financial Services Agency)

**Citation (出典表記):**

> 金融庁「経済価値ベースのソルベンシー規制におけるイールド・カーブ作成ツール」（2026 年 3 月末基準日版）

**English citation:**

> Financial Services Agency of Japan, *Yield curve creation tool for the economic
> value-based solvency regulation*, version for the 31 March 2026 valuation date

| Item | Details |
| --- | --- |
| File | `reproduction/bel_demo/data/external/fsa_esr/esr_yield_curve_tool_20260331.xlsx` (the file as downloaded, unmodified) |
| Provider | https://www.fsa.go.jp/policy/economic_value-based_solvency/20260323/20260323.html (a permanent page linked from the ESR portal page; the file is replaced at each valuation date) |
| Version identification | The valuation date stated inside the workbook is 「2026年3月末」 (end of March 2026). The file's last-modified timestamp is 2026-04-06; retrieved locally on 2026-07-28 |
| Use | Discount-rate curve for the BEL sensitivity demo in §8 (reads the LOT, convergence maturity, UFR, and zero-coupon rates from the JPY row of the parameter sheet and reproduces the Smith-Wilson extrapolation) |
| Terms of use | Subject to the terms of use of the FSA website (https://www.fsa.go.jp/rules/index.html ). Conforms to the Government of Japan Standard Terms of Use; reproduction, adaptation, and commercial use are permitted with attribution |

**On derived outputs:** `reproduction/bel_demo/build_esr_discount_curve.py` reads the parameters of the tool above and then **independently re-implements** the Smith-Wilson logic to generate `esr_jpy_spot_curve_20260331.csv`. It has not been verified that this implementation is identical to the SW sheet of the tool itself. The FSA bears no responsibility for the results of this re-implementation.

---

## Disclaimer

All derived data and analysis results in this repository are the work of the authors
of this study and do not represent the views of any of the providers listed above.
