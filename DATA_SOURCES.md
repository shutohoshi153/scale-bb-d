# Data Sources

This page credits the third-party data bundled in this repository and states
the terms under which it is redistributed. The repository's own licenses
(MIT for code, CC BY 4.0 for the figures) do **not** extend to these
datasets; each remains subject to the terms of its provider.

---

## 1. Vital Statistics of Japan (Ministry of Health, Labour and Welfare / e-Stat)

**Citation (English):**

> Vital Statistics of Japan, Ministry of Health, Labour and Welfare
> (Portal Site of Official Statistics of Japan, e-Stat)

**Citation (Japanese, as requested by the provider):**

> 厚生労働省「人口動態調査」（政府統計の総合窓口 e-Stat）

| Item | Detail |
| --- | --- |
| Bundled file | `reproduction/backtest/data/raw/estat_5-15_deaths_by_cause_sex_age_0003411659.csv` |
| Original table | e-Stat statistical table ID **0003411659** — "Table 5-15: Deaths and death rates by cause of death (selected causes), sex and age (5-year groups)", 1950–2024. The file is the unmodified download; only the file name has been transliterated for this repository (original name: `5-15_死因_性_5歳階級_年次_死亡数率__0003411659.csv`) |
| Derived files | `reproduction/backtest/data/prebuilt_disease_panel_mortality.csv`, `reproduction/generational/KDB/data/processed/mortality_apc_panel.csv` / `.parquet` |
| Role in the paper | Primary input of the study: cause-specific mortality rates for the full pipeline of §3.1–§3.4 |
| Terms of use | Government of Japan Standard Terms of Use (version 2.0): reproduction, adaptation and commercial use are permitted with attribution. https://www.e-stat.go.jp/terms-of-use |

**Derived data:** the panel files listed above were produced by the authors'
scripts from the original table. The Ministry of Health, Labour and Welfare is
not responsible for the processed figures.

---

## Disclaimer

All derived data and analysis results in this repository are the work of the
authors and do not represent the views of the data provider above. This
repository presents academic research based on publicly available data; it
does not guarantee the profitability or capital requirements of any specific
insurance product.
