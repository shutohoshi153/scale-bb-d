"""全国がん登録 (NCR) の罹患率から発生率パネルを構築する.

入力:
    data/RowData/cancer_incidenceNCR(2016-2023).xls
        - `rate` シート: 罹患率(人口10万対) × 部位 × 性 × 年 × 5歳階級
        - `number` シート: 罹患数 (numerator_count の実績値)
        - `pop` シート: 分母人口 (暦年 × 性 × 5歳階級)
        - `部位コード表` シート: 部位コード - ICD-10 対応

手法:
    NCR の粗罹患率は **真の incidence rate そのもの** であり、
    そのまま年率化 (÷100,000) して採用する。quality_flag='A' (最高品質)。

出力 (incidence_panel schema):
    rate_type      = 'registry'
    section        = 'onset'
    disease_id     = 'cancer' (コード=1 全部位のみ) / NaN (部位別)
    disease_norm   = 部位日本語名
    icd10          = ICD-10 コード範囲
    quality_flag   = 'A'
    year           = 2016-2023
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from panel_helpers import (
    PROJECT_ROOT,
    ROW_DATA,
    conform_incidence_panel,
    empty_incidence_panel,
    normalize_sex,
    parse_age_label,
    sex_code,
)


NCR_PATH = ROW_DATA / "cancer_incidenceNCR(2016-2023).xls"

AGE_COLUMNS = [
    "0-4歳",
    "5-9歳",
    "10-14歳",
    "15-19歳",
    "20-24歳",
    "25-29歳",
    "30-34歳",
    "35-39歳",
    "40-44歳",
    "45-49歳",
    "50-54歳",
    "55-59歳",
    "60-64歳",
    "65-69歳",
    "70-74歳",
    "75-79歳",
    "80-84歳",
    "85-89歳",
    "90-94歳",
    "95-99歳",
    "100歳以上",
]
RECAP_COLUMNS = ["85歳以上（再掲）", "95歳以上（再掲）"]
UNKNOWN_COLUMNS = ["不詳"]
TOTAL_COLUMN = "粗率"


def _load_rate() -> pd.DataFrame:
    df = pd.read_excel(NCR_PATH, sheet_name="rate", header=0)
    df = df.rename(columns=lambda c: str(c).strip())
    return df


def _load_number() -> pd.DataFrame:
    df = pd.read_excel(NCR_PATH, sheet_name="number", header=0)
    df = df.rename(columns=lambda c: str(c).strip())
    return df


def _load_population() -> pd.DataFrame:
    """pop シートを long に変換して返す.

    columns:
        year (int), sex (total/male/female), age_code, age_low, age_high,
        population_thousand
    """
    df = pd.read_excel(NCR_PATH, sheet_name="pop", header=0)
    df = df.rename(columns=lambda c: str(c).strip())

    id_vars = ["人口", "性別", "暦年"]
    age_like_cols = [c for c in df.columns if c not in id_vars and c != "全年齢"]

    melted = df.melt(
        id_vars=id_vars, value_vars=age_like_cols, var_name="age_label", value_name="pop_raw"
    )
    melted = melted[melted["人口"] == "総人口"]
    melted["sex"] = melted["性別"].map(normalize_sex)
    melted["year"] = pd.to_numeric(melted["暦年"], errors="coerce").astype("Int64")

    ages = melted["age_label"].map(parse_age_label)
    melted["age_code"] = [a.code for a in ages]
    melted["age_low"] = [a.low for a in ages]
    melted["age_high"] = [a.high for a in ages]
    melted["age_is_recap"] = [a.is_recap for a in ages]
    melted["age_is_total"] = [a.is_total for a in ages]

    # NCR pop は人単位。千人に変換
    melted["population_thousand"] = pd.to_numeric(
        melted["pop_raw"], errors="coerce"
    ) / 1000.0

    keep = [
        "year",
        "sex",
        "age_code",
        "age_low",
        "age_high",
        "age_is_recap",
        "age_is_total",
        "population_thousand",
    ]
    return melted[keep].dropna(subset=["year", "population_thousand"])


def build() -> pd.DataFrame:
    if not NCR_PATH.exists():
        print(f"[registry] {NCR_PATH} not found, skipping")
        return empty_incidence_panel()

    rate = _load_rate()
    pop = _load_population()

    # wide → long (年齢軸のみ melt)
    value_cols = AGE_COLUMNS + RECAP_COLUMNS
    id_vars = ["コード", "部位", "ICD-10", "性別", "診断年"]
    melted = rate.melt(
        id_vars=id_vars,
        value_vars=value_cols,
        var_name="age_label",
        value_name="rate_per_100k",
    )

    # "-" 等の欠測を NaN に
    melted["rate_per_100k"] = pd.to_numeric(melted["rate_per_100k"], errors="coerce")

    ages = melted["age_label"].map(parse_age_label)
    melted["age_code"] = [a.code for a in ages]
    melted["age_low"] = [a.low for a in ages]
    melted["age_high"] = [a.high for a in ages]
    melted["age_is_recap"] = [a.is_recap for a in ages]
    melted["age_is_total"] = [a.is_total for a in ages]

    melted["sex"] = melted["性別"].map(normalize_sex)
    melted["year"] = pd.to_numeric(melted["診断年"], errors="coerce").astype("Int64")

    # disease_id マッピング:
    #   コード=1 (全部位) → 'cancer'
    #   コード=101 (全部位(上皮内がん含む)) → 'cancer_with_insitu'
    code_to_disease_id = {1: "cancer", 101: "cancer_with_insitu"}
    melted["disease_id"] = melted["コード"].map(code_to_disease_id)
    # 部位名: 空白正規化だけ
    melted["disease_norm"] = melted["部位"].astype(str).str.strip()
    melted["icd10"] = melted["ICD-10"].astype(str).str.strip()

    # 再掲・欠測行は保持しつつフラグで分離
    melted = melted.dropna(subset=["rate_per_100k", "age_low", "year"])

    # 分子数 (number シート) を年齢ごとに結合
    num = _load_number()
    num_melted = num.melt(
        id_vars=id_vars,
        value_vars=value_cols,
        var_name="age_label",
        value_name="numerator_count",
    )
    num_melted["numerator_count"] = pd.to_numeric(
        num_melted["numerator_count"], errors="coerce"
    )
    key_cols = ["コード", "性別", "診断年", "age_label"]
    merged = melted.merge(num_melted[key_cols + ["numerator_count"]], on=key_cols, how="left")

    # 人口結合 (NCR の pop シート由来)
    pop_key = pop.set_index(["year", "sex", "age_code"])["population_thousand"].to_dict()
    merged["population_thousand"] = merged.apply(
        lambda r: pop_key.get((int(r["year"]), r["sex"], r["age_code"])), axis=1
    )

    out = pd.DataFrame(
        {
            "disease_id": merged["disease_id"],
            "disease_norm": merged["disease_norm"],
            "icd10": merged["icd10"],
            "sex": merged["sex"],
            "sex_code": merged["sex"].map(sex_code),
            "age_code": merged["age_code"],
            "age_low": merged["age_low"].astype("Int64"),
            "age_high": merged["age_high"].astype("Int64"),
            "year": merged["year"].astype("Int64"),
            "section": "onset",
            "rate_type": "registry",
            "incidence_rate_annual": merged["rate_per_100k"].astype(float) / 100_000.0,
            "incidence_rate_per_100k": merged["rate_per_100k"].astype(float),
            "numerator_count": merged["numerator_count"],
            "population_thousand": merged["population_thousand"],
            "source_table": "cancer_incidenceNCR(2016-2023).xls",
            "quality_flag": "A",
            "method_note": "全国がん登録の粗罹患率 (真のincidence)",
        }
    )

    return conform_incidence_panel(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="registry ベース発生率パネル生成")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    df = build()
    print(f"[registry] {len(df)} rows")
    if not df.empty:
        print("[registry] disease_id × year counts:")
        print(
            df.groupby(["disease_id", "year"], dropna=False)
            .size()
            .unstack(fill_value=0)
            .to_string()
        )
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"[registry] saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
