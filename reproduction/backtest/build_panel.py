"""Build an age x year mortality panel for each disease of the study (§3.1).

Source: data/raw/estat_5-15_deaths_by_cause_sex_age_0003411659.csv — e-Stat
table 5-15 (deaths and death rates by cause of death, sex, 5-year age group
and year ["死因_性_5歳階級_年次_死亡数率"], 1950-2024).

Output: data/disease_panel_mortality.csv
        columns: disease_id, sex, year, age_low, age_high, rate_per_100k, deaths
"""
from __future__ import annotations
import pandas as pd

# [REPRO] Paths consolidated in the self-contained path layer
# (originally: relative references from ROOT=parents[2])
import _paths

SRC = _paths.RAW_VITAL_CSV
OUT_DIR = _paths.DATA_DIR
OUT_DIR.mkdir(parents=True, exist_ok=True)

# disease_id -> cause-of-death trend classification code ("死因年次推移分類_code",
# Hi-code in table 5-15).
# The trend classification was revised in 2017; for malignant neoplasms
# (Hi02 -> Hi022017) and hypertensive diseases (Hi04 -> Hi042017), the entire
# 1950-2024 period is stored under the 2017-revision codes.
DISEASE_TO_HICODE = {
    "cancer": "Hi022017",
    "diabetes": "Hi03",
    "hypertensive": "Hi042017",
    "heart_disease": "Hi05",  # heart diseases (excl. hypertensive). Common slug across the paper and both reproduction packages
    "cerebrovascular": "Hi06",
    "liver": "Hi11",
    "kidney": "Hi12",  # renal failure (closest 5-15 category; includes glomerular diseases etc.)
    "total": "Hi00",
}

# heart_ischemic (ischaemic heart diseases) is NOT in the cause-of-death trend
# classification; it appears only in the condensed cause-of-death list (5-28),
# which lacks 5-year age groups. We skip it here and note in the README.

# Japanese age-group labels as they appear in the e-Stat CSV (data-facing;
# keys must stay byte-identical). "総数" = all ages, "不詳" = age unknown.
AGE_LABEL_TO_LOW = {
    "総数": None,
    "0～4歳": 0,
    "5～9歳": 5,
    "10～14歳": 10,
    "15～19歳": 15,
    "20～24歳": 20,
    "25～29歳": 25,
    "30～34歳": 30,
    "35～39歳": 35,
    "40～44歳": 40,
    "45～49歳": 45,
    "50～54歳": 50,
    "55～59歳": 55,
    "60～64歳": 60,
    "65～69歳": 65,
    "70～74歳": 70,
    "75～79歳": 75,
    "80～84歳": 80,
    "85～89歳": 85,
    "90～94歳": 90,
    "95～99歳": 95,
    "100歳以上": 100,
    "不詳": None,
}


def main():
    raw = pd.read_csv(SRC)
    # column names sometimes have a BOM prefix; strip
    raw.columns = [c.replace("﻿", "") for c in raw.columns]
    print(f"loaded {len(raw):,} rows")
    print("years range:", raw["時間軸(年次)"].min(), "→", raw["時間軸(年次)"].max())

    # Filter on tabulated item ("表章項目"): "死亡数" = deaths,
    # "死亡率" = death rate (per 100k population)
    deaths = raw[raw["表章項目"] == "死亡数"].copy()
    rate = raw[raw["表章項目"] == "死亡率"].copy()

    # Sex column ("性別") -> sex slug ("総数"=total, "男"=male, "女"=female)
    sex_map = {"総数": "total", "男": "male", "女": "female"}
    rate["sex"] = rate["性別"].map(sex_map)
    deaths["sex"] = deaths["性別"].map(sex_map)

    # Age column ("年齢(5歳階級)", 5-year groups) -> age_low
    # (use label for stability across encodings)
    rate["age_low"] = rate["年齢(5歳階級)"].map(AGE_LABEL_TO_LOW)
    deaths["age_low"] = deaths["年齢(5歳階級)"].map(AGE_LABEL_TO_LOW)

    # Year column ("時間軸(年次)") -> int (strip the "年" [year] suffix)
    rate["year"] = rate["時間軸(年次)"].str.replace("年", "").astype(int)
    deaths["year"] = deaths["時間軸(年次)"].str.replace("年", "").astype(int)

    # Cause of death -> disease_id
    # "死因年次推移分類_code" looks like "Hi02" / "Hi00" (Hi00 = all causes)
    print("sample hi codes:", rate["死因年次推移分類_code"].unique())

    rate["hi_code"] = rate["死因年次推移分類_code"].astype(str)
    deaths["hi_code"] = deaths["死因年次推移分類_code"].astype(str)

    hi_to_disease = {h: d for d, h in DISEASE_TO_HICODE.items()}

    rate["disease_id"] = rate["hi_code"].map(hi_to_disease)
    deaths["disease_id"] = deaths["hi_code"].map(hi_to_disease)

    rate = rate.dropna(subset=["disease_id", "sex", "age_low"])
    deaths = deaths.dropna(subset=["disease_id", "sex", "age_low"])

    rate["age_low"] = rate["age_low"].astype(int)
    deaths["age_low"] = deaths["age_low"].astype(int)

    rate_out = rate[["disease_id", "sex", "year", "age_low", "value"]].rename(
        columns={"value": "rate_per_100k"}
    )
    deaths_out = deaths[["disease_id", "sex", "year", "age_low", "value"]].rename(
        columns={"value": "deaths"}
    )

    merged = rate_out.merge(deaths_out, on=["disease_id", "sex", "year", "age_low"], how="left")
    merged = merged.sort_values(["disease_id", "sex", "year", "age_low"]).reset_index(drop=True)

    out_csv = OUT_DIR / "disease_panel_mortality.csv"
    merged.to_csv(out_csv, index=False)
    print(f"wrote {out_csv}  rows={len(merged):,}")
    print()
    print("panel summary:")
    summary = merged.groupby(["disease_id", "sex"]).agg(
        n_rows=("rate_per_100k", "size"),
        n_years=("year", "nunique"),
        n_ages=("age_low", "nunique"),
        year_min=("year", "min"),
        year_max=("year", "max"),
    ).reset_index()
    print(summary.to_string(index=False))
    summary.to_csv(OUT_DIR / "panel_summary.csv", index=False)


if __name__ == "__main__":
    main()
