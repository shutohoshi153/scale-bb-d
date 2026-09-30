"""外来初診受療率ベースの疾病発生率パネルを構築する.

入力:
    data/RowData/estat_processed/patient_survey/Z70__0004025963.csv
        外来受療率(人口10万対) × 性 × 5歳年齢階級 × 傷病分類 × 外来(初診/再来)
        2023 年断面、12,960 行

手法:
    incidence_rate_annual
      = 初診受療率(人口10万対) / 100,000
        × initial_visit_annual_days
        × initial_visit_duplicate_adjust

出力:
    rate_type = 'initial_visit'
    section   = 'onset' (新規発症相当)
    quality_flag = 'B'

注意:
    患者調査は単日断面調査のため、年率化は config で指定された
    年換算係数を乗じる近似推計である。文献的には K=200-250 程度が
    目安となるが、疾病によっては過大/過小評価の可能性がある。
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml

from panel_helpers import (
    PATIENT_SURVEY,
    PROCESSED,
    PROJECT_ROOT,
    conform_incidence_panel,
    empty_incidence_panel,
    focus_disease_id,
    normalize_disease_label,
    normalize_sex,
    parse_age_label,
    sex_code,
)


Z70_PATH = PATIENT_SURVEY / "Z70__0004025963.csv"


def _load_config() -> dict:
    path = PROJECT_ROOT / "config.yaml"
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_population_2023() -> pd.DataFrame:
    """2023 年の性×5歳年齢階級別人口 (千人) を返す."""
    from panel_helpers import load_population

    pop = load_population()
    pop = pop[pop["year"] == 2023]
    pop = pop[~pop["age_is_recap"] & ~pop["age_is_total"]]
    return pop[["sex", "age_code", "age_low", "age_high", "population_thousand"]]


def build() -> pd.DataFrame:
    if not Z70_PATH.exists():
        print(f"[initial_visit] {Z70_PATH} not found, skipping")
        return empty_incidence_panel()

    cfg = _load_config().get("incidence", {})
    annual_days = float(cfg.get("initial_visit_annual_days", 240))
    dup_adjust = float(cfg.get("initial_visit_duplicate_adjust", 0.7))

    src = pd.read_csv(Z70_PATH)

    # 初診/再来 軸を "初診" のみ抽出（外来/初診/再来 の 3 値）
    src = src[src["外来（初診－再来）_002"] == "初診"].copy()
    if src.empty:
        print("[initial_visit] no '初診' rows found")
        return empty_incidence_panel()

    # 年齢・性別・疾病を正規化
    ages = src["年齢階級_006"].map(parse_age_label)
    src["age_code"] = [a.code for a in ages]
    src["age_low"] = [a.low for a in ages]
    src["age_high"] = [a.high for a in ages]
    src["age_is_recap"] = [a.is_recap for a in ages]
    src["age_is_total"] = [a.is_total for a in ages]
    src["sex"] = src["性別_001"].map(normalize_sex)
    src["disease_norm"] = src["傷病分類_004"].map(normalize_disease_label)
    src["disease_id"] = src["disease_norm"].map(focus_disease_id)

    # 総数・再掲を除外
    src = src[~src["age_is_total"] & ~src["age_is_recap"]]
    src = src[src["disease_norm"] != ""]
    src = src.dropna(subset=["age_low", "age_high", "value"])

    src["rate_per_100k_daily"] = src["value"].astype(float)
    src["incidence_rate_per_100k"] = (
        src["rate_per_100k_daily"] * annual_days * dup_adjust
    )
    src["incidence_rate_annual"] = src["incidence_rate_per_100k"] / 100_000.0

    # 人口結合 (分子件数の推計用)
    pop = _load_population_2023()
    merged = src.merge(pop, on=["sex", "age_code"], how="left", suffixes=("", "_p"))
    merged["numerator_count"] = (
        merged["incidence_rate_annual"] * merged["population_thousand"] * 1000.0
    )
    # age_low/age_high は結合後どちらかを残す
    merged["age_low"] = merged["age_low"].fillna(merged["age_low_p"])
    merged["age_high"] = merged["age_high"].fillna(merged["age_high_p"])

    out = pd.DataFrame(
        {
            "disease_id": merged["disease_id"],
            "disease_norm": merged["disease_norm"],
            "icd10": pd.NA,
            "sex": merged["sex"],
            "sex_code": merged["sex"].map(sex_code),
            "age_code": merged["age_code"],
            "age_low": merged["age_low"].astype("Int64"),
            "age_high": merged["age_high"].astype("Int64"),
            "year": 2023,
            "section": "onset",
            "rate_type": "initial_visit",
            "incidence_rate_annual": merged["incidence_rate_annual"],
            "incidence_rate_per_100k": merged["incidence_rate_per_100k"],
            "numerator_count": merged["numerator_count"],
            "population_thousand": merged["population_thousand"],
            "source_table": "Z70__0004025963",
            "quality_flag": "B",
            "method_note": (
                f"Z70外来初診受療率(日次/10万対) × {annual_days}日 × "
                f"重複補正{dup_adjust}"
            ),
        }
    )

    return conform_incidence_panel(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="initial_visit ベース発生率パネル生成")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    df = build()
    print(f"[initial_visit] {len(df)} rows")
    if not df.empty:
        print("[initial_visit] disease_id counts:")
        print(df.groupby("disease_id", dropna=False).size().to_string())
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"[initial_visit] saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
