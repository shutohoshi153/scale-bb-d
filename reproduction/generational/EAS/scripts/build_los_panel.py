"""退院患者平均在院日数 (LOS) パネル.

入力:
    data/RowData/estat_processed/patient_survey/H20-47__0003013497.csv
        平成20年患者調査 第47表
        性×年齢階級×傷病分類×病院-一般診療所別 平均在院日数(日)

出力:
    DataFrame (PROCESSED/los_panel.csv)
        disease_norm, sex, age_code, age_low, age_high, facility,
        los_days
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from panel_helpers import (
    PATIENT_SURVEY,
    PROCESSED,
    normalize_disease_label,
    normalize_sex,
    parse_age_label,
)


LOS_PATH = PATIENT_SURVEY / "H20-47__0003013497.csv"


def build() -> pd.DataFrame:
    if not LOS_PATH.exists():
        print(f"[los] {LOS_PATH} not found")
        return pd.DataFrame()

    df = pd.read_csv(LOS_PATH)

    ages = df["年齢階級"].map(parse_age_label)
    df["age_code"] = [a.code for a in ages]
    df["age_low"] = [a.low for a in ages]
    df["age_high"] = [a.high for a in ages]
    df["age_is_recap"] = [a.is_recap for a in ages]
    df["age_is_total"] = [a.is_total for a in ages]

    df["sex"] = df["性"].map(normalize_sex)
    df["disease_norm"] = df["傷病分類１"].map(normalize_disease_label)
    df["facility"] = df["施設の種類（病院ー一般診療所）"]
    df["los_days"] = pd.to_numeric(df["value"], errors="coerce")

    keep = [
        "disease_norm",
        "sex",
        "age_code",
        "age_low",
        "age_high",
        "age_is_recap",
        "age_is_total",
        "facility",
        "los_days",
    ]
    out = df[keep].dropna(subset=["los_days"])
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="LOS パネル生成")
    parser.add_argument(
        "--output", default=str(PROCESSED / "los_panel.csv"), help="出力 CSV パス"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="生成結果が空でも既存ファイルを上書きする",
    )
    args = parser.parse_args()
    df = build()
    print(f"[los] {len(df)} rows")
    if args.output:
        out = Path(args.output)
        # 入力の e-Stat 生データ未同梱時は build() が空を返す。そのまま書くと
        # 同梱済み los_panel.csv を空ファイルで潰すため中止する (README §2 参照)。
        if df.empty and out.exists() and not args.force:
            print(
                f"[abort] 生成結果が 0 行のため、既存の {out} を上書きしません。\n"
                "        入力 (data/RowData/estat_processed/patient_survey/) が"
                "同梱されていない可能性があります。\n"
                "        意図的に上書きする場合は --force を付けてください。"
            )
            return 1
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"[los] saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
