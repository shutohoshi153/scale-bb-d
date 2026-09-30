"""退院フローベースの疾病発生率パネル.

手法:
    Z10 (推計入院患者数、stock) × 365 / 平均在院日数 = 年間新規入院数 (flow)
    年間新規入院数 ÷ 人口 = 入院発生率 (annual)

    これは Little の法則 (stock = flow × duration) の逆変換。
    入院イベントを疾病発生の代理とする quality_flag='C'。

入力:
    data/RowData/estat_processed/patient_survey/Z10__0004025900.csv (2023)
    data/RowData/estat_processed/patient_survey/H20-47__0003013497.csv (平均在院日数)
    data/RowData/estat_processed/population/pop_5yr_age_combined.csv

出力:
    rate_type = 'discharge'
    section   = 'inpatient'
    quality_flag = 'C'
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml

from build_los_panel import build as build_los_raw
from panel_helpers import (
    PATIENT_SURVEY,
    PROCESSED,
    PROJECT_ROOT,
    conform_incidence_panel,
    empty_incidence_panel,
    focus_disease_id,
    load_population,
    normalize_disease_label,
    normalize_sex,
    parse_age_label,
    sex_code,
)


Z10_PATH = PATIENT_SURVEY / "Z10__0004025900.csv"


def _load_config() -> dict:
    path = PROJECT_ROOT / "config.yaml"
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _prepare_los(los_df: pd.DataFrame) -> pd.DataFrame:
    """LOS を (disease_norm, sex, age_code) 粒度に集約 (総数施設)."""
    df = los_df[los_df["facility"] == "総数"].copy()
    df = df[~df["age_is_total"] & ~df["age_is_recap"]]
    return df[["disease_norm", "sex", "age_code", "los_days"]]


def _los_disease_keys(disease_norm: str) -> list[str]:
    """LOS 側の粒度に合わせた candidate 突合キーを返す.

    Z10  : '新生物＜腫瘍＞', '　（悪性新生物＜腫瘍＞）（再掲）'
    LOS  : '新生物',       '　（悪性新生物）（再掲）'

    の差分を吸収するため、'＜腫瘍＞' 除去版でも検索できるようにする。
    """
    if not disease_norm:
        return []
    variants = [disease_norm]
    for trim in ("＜腫瘍＞", "<腫瘍>"):
        if trim in disease_norm:
            variants.append(disease_norm.replace(trim, ""))
    return variants


def build() -> pd.DataFrame:
    if not Z10_PATH.exists():
        print(f"[discharge] {Z10_PATH} not found, skipping")
        return empty_incidence_panel()

    cfg = _load_config().get("incidence", {})
    annual_days = float(cfg.get("discharge_annual_days", 365))
    los_default = float(cfg.get("los_default", 33.3))

    z10 = pd.read_csv(Z10_PATH)
    # 総数 (病院＋一般診療所) のみ使用
    z10 = z10[z10["施設の種類（病院ー一般診療所）"] == "総数"].copy()

    ages = z10["年齢階級"].map(parse_age_label)
    z10["age_code"] = [a.code for a in ages]
    z10["age_low"] = [a.low for a in ages]
    z10["age_high"] = [a.high for a in ages]
    z10["age_is_recap"] = [a.is_recap for a in ages]
    z10["age_is_total"] = [a.is_total for a in ages]
    z10["sex"] = z10["性"].map(normalize_sex)
    z10["disease_norm"] = z10["傷病分類２"].map(normalize_disease_label)
    z10["disease_id"] = z10["disease_norm"].map(focus_disease_id)
    z10["inpatient_thousand"] = pd.to_numeric(z10["value"], errors="coerce")

    z10 = z10[~z10["age_is_total"] & ~z10["age_is_recap"]]
    z10 = z10.dropna(subset=["inpatient_thousand", "age_low"])

    # LOS 準備
    los_raw = build_los_raw()
    los = _prepare_los(los_raw)
    # disease_norm の正規化 (LOS 側も normalize をかけておく)
    los["disease_norm"] = los["disease_norm"].map(normalize_disease_label)

    los_key = {
        (d, s, a): v
        for d, s, a, v in zip(
            los["disease_norm"], los["sex"], los["age_code"], los["los_days"]
        )
    }

    def lookup_los(d: str, s: str, a: str) -> float:
        for cand in _los_disease_keys(d):
            v = los_key.get((cand, s, a))
            if v is not None:
                return float(v)
        # fallback 1: sex='total'
        for cand in _los_disease_keys(d):
            v = los_key.get((cand, "total", a))
            if v is not None:
                return float(v)
        # fallback 2: age='total'
        for cand in _los_disease_keys(d):
            v = los_key.get((cand, s, "total"))
            if v is not None:
                return float(v)
        # fallback 3: both 'total'
        for cand in _los_disease_keys(d):
            v = los_key.get((cand, "total", "total"))
            if v is not None:
                return float(v)
        # fallback 4: config default
        return los_default

    z10["los_days"] = z10.apply(
        lambda r: lookup_los(r["disease_norm"], r["sex"], r["age_code"]), axis=1
    )

    # 人口結合
    pop = load_population()
    pop = pop[(pop["year"] == 2023) & ~pop["age_is_recap"] & ~pop["age_is_total"]]
    pop_key = pop.set_index(["sex", "age_code"])["population_thousand"].to_dict()
    z10["population_thousand"] = z10.apply(
        lambda r: pop_key.get((r["sex"], r["age_code"])), axis=1
    )

    # 新規入院数 (千人/年) = Z10 × annual_days / LOS
    z10["new_admission_thousand"] = (
        z10["inpatient_thousand"] * annual_days / z10["los_days"]
    )

    # 発生率 (年率)
    z10 = z10.dropna(subset=["population_thousand"])
    z10 = z10[z10["population_thousand"] > 0]
    z10["incidence_rate_annual"] = (
        z10["new_admission_thousand"] / z10["population_thousand"]
    )
    z10["incidence_rate_per_100k"] = z10["incidence_rate_annual"] * 100_000.0
    z10["numerator_count"] = z10["new_admission_thousand"] * 1000.0

    out = pd.DataFrame(
        {
            "disease_id": z10["disease_id"],
            "disease_norm": z10["disease_norm"],
            "icd10": pd.NA,
            "sex": z10["sex"],
            "sex_code": z10["sex"].map(sex_code),
            "age_code": z10["age_code"],
            "age_low": z10["age_low"].astype("Int64"),
            "age_high": z10["age_high"].astype("Int64"),
            "year": 2023,
            "section": "inpatient",
            "rate_type": "discharge",
            "incidence_rate_annual": z10["incidence_rate_annual"],
            "incidence_rate_per_100k": z10["incidence_rate_per_100k"],
            "numerator_count": z10["numerator_count"],
            "population_thousand": z10["population_thousand"],
            "source_table": "Z10__0004025900+H20-47__0003013497",
            "quality_flag": "C",
            "method_note": (
                "Z10入院患者数 × {ad}日 ÷ 平均在院日数(H20) → 年間新規入院数 → "
                "÷人口"
            ).format(ad=int(annual_days)),
        }
    )

    return conform_incidence_panel(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="discharge ベース発生率パネル生成")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    df = build()
    print(f"[discharge] {len(df)} rows")
    if not df.empty:
        print("[discharge] disease_id counts:")
        print(df.groupby("disease_id", dropna=False).size().to_string())
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"[discharge] saved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
