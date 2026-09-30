"""Build age x year mortality panel for each disease in disease_estat_mapping.csv.

Source: ScaleBB_Research/data/raw/estat_processed/vital_statistics/5-15_*
(死因_性_5歳階級_年次_死亡数率, 1950-2024).

Output: BackTest_ScaleBB_2015_2024/data/disease_panel_mortality.csv
        columns: disease_id, sex, year, age_low, age_high, rate_per_100k, deaths
"""
from __future__ import annotations
import pandas as pd

# [REPRO] パスは自己完結パス層に集約 (元: ROOT=parents[2] からの相対参照)
import _paths

SRC = _paths.RAW_VITAL_CSV
MAPPING = _paths.DISEASE_MAPPING
OUT_DIR = _paths.DATA_DIR
OUT_DIR.mkdir(parents=True, exist_ok=True)

# disease_id -> 死因年次推移分類_code (Hi-code in 5-15).
# 2017年に死因年次推移分類が改定されており、悪性新生物(Hi02→Hi022017)・
# 高血圧性疾患(Hi04→Hi042017) は 1950-2024 全期間が 2017版コードに格納される。
DISEASE_TO_HICODE = {
    "cancer": "Hi022017",
    "diabetes": "Hi03",
    "hypertensive": "Hi042017",
    "heart_disease": "Hi05",  # 心疾患(高血圧性を除く)。論文・両再現パッケージで共通スラグ
    "cerebrovascular": "Hi06",
    "liver": "Hi11",
    "kidney": "Hi12",  # 腎不全 (糸球体疾患等を含む 5-15 上の最も近い区分)
    "total": "Hi00",
}

# heart_ischemic (虚血性心疾患) is NOT in 死因年次推移分類; only in 死因簡単分類 (5-28)
# which lacks 5歳階級. We skip it here and note in the README.

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

    # Filter: 表章項目=死亡率 (人口10万対)
    deaths = raw[raw["表章項目"] == "死亡数"].copy()
    rate = raw[raw["表章項目"] == "死亡率"].copy()

    # 性別 -> sex slug
    sex_map = {"総数": "total", "男": "male", "女": "female"}
    rate["sex"] = rate["性別"].map(sex_map)
    deaths["sex"] = deaths["性別"].map(sex_map)

    # 年齢 -> age_low (use label for stability across encodings)
    rate["age_low"] = rate["年齢(5歳階級)"].map(AGE_LABEL_TO_LOW)
    deaths["age_low"] = deaths["年齢(5歳階級)"].map(AGE_LABEL_TO_LOW)

    # 年次 -> int
    rate["year"] = rate["時間軸(年次)"].str.replace("年", "").astype(int)
    deaths["year"] = deaths["時間軸(年次)"].str.replace("年", "").astype(int)

    # 死因 -> disease_id
    # 死因年次推移分類_code looks like "Hi02" / "Hi00" (Hi00 = 総数)
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
