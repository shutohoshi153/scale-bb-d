"""死亡率ベースの発生率パネルを構築する.

入力:
    data/processed/mortality_apc_panel.parquet (既存)
        人口動態 5-15 由来の死因×年齢×性×年 パネル

出力:
    DataFrame (incidence_panel schema, rate_type='mortality')

主にクロスチェック・致死率が高い疾患 (cancer, cerebrovascular) の発生率近似に
使用する。'mortality' は真の incidence の下限になることに注意。
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from panel_helpers import (
    INCIDENCE_PANEL_COLUMNS,
    PROCESSED,
    conform_incidence_panel,
    empty_incidence_panel,
    sex_code,
)


def build(mortality_path: Path | None = None) -> pd.DataFrame:
    mortality_path = mortality_path or (PROCESSED / "mortality_apc_panel.parquet")
    if not mortality_path.exists():
        print(f"[mortality] {mortality_path} not found, skipping")
        return empty_incidence_panel()

    src = pd.read_parquet(mortality_path)

    # 総数・再掲を除外
    src = src[~src["age_is_total"].fillna(False)]
    src = src[~src["age_is_recap"].fillna(False)]

    src = src.dropna(subset=["age_low", "rate_per_100k", "year"])
    src = src[src["sex"].isin(["total", "male", "female"])]

    out = pd.DataFrame(
        {
            "disease_id": src["disease_id"],
            "disease_norm": src["disease_raw"],
            "icd10": pd.NA,
            "sex": src["sex"],
            "sex_code": src["sex"].map(sex_code),
            "age_code": src["age_code"],
            "age_low": src["age_low"].astype("Int64"),
            "age_high": src["age_high"].astype("Int64"),
            "year": src["year"].astype(int),
            "section": "onset",
            "rate_type": "mortality",
            "incidence_rate_annual": src["rate_per_100k"].astype(float) / 100_000.0,
            "incidence_rate_per_100k": src["rate_per_100k"].astype(float),
            "numerator_count": src["deaths"].astype(float),
            "population_thousand": src["population_thousand"].astype(float),
            "source_table": "vital_5-15__0003411659",
            "quality_flag": "D",
            "method_note": "人口動態 5-15 の粗死亡率をそのまま incidence 下限として採用",
        }
    )
    return conform_incidence_panel(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="mortality ベースの発生率パネル生成")
    parser.add_argument("--output", default=None, help="出力 CSV パス (省略時は標準出力のみ)")
    args = parser.parse_args()

    df = build()
    print(f"[mortality] {len(df)} rows")
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"[mortality] saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
