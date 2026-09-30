"""標準生命表 (アクチュアリー会公表) と人口発生率 (mortality) の整合性検証.

data/lifetable/seimeihyo960718.xlsx に格納されている以下 7 系統の
年齢別死亡率を読み込み、tidy 形式の DataFrame に整形する:

    - 生保標準生命表2018 (死亡保険用)
    - 第三分野標準生命表2018
    - 生保標準生命表2007 (死亡保険用)
    - 生保標準生命表2007 (年金開始後用)
    - 第三分野標準生命表2007
    - 生保標準生命表1996 (死亡保険用)
    - 生保標準生命表1996 (年金開始後用)

続いて `experience_rate.db` の `population_incidence` (rate_type='mortality')
と年齢帯を揃えて突合し、以下を算出する:

    ratio = population_rate / standard_rate

保険数理上、以下の挙動が期待される:
    - 死亡保険用 標準生命表 : 安全割増のため population より高めの死亡率
      → ratio < 1.0 (特に若年・中年帯)
    - 年金開始後用 (生保標準) : 長生きリスク用。population より低め
      → ratio > 1.0
    - 第三分野 (医療) : 罹患概念。本比較では参考値
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
XLSX_PATH = PROJECT_ROOT / "data" / "lifetable" / "seimeihyo960718.xlsx"
DB_PATH = PROJECT_ROOT / "experience_rate.db"
OUT_DIR = PROJECT_ROOT / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 列マッピング: seimeihyo960718.xlsx の列レイアウト
# col 0: 空, col 1: 年齢
# col 2-3: 標準2018 死亡保険用 (男/女)
# col 4-5: 第三分野標準2018 (男/女)
# col 6-7: 標準2007 死亡保険用 (男/女)
# col 8-9: 標準2007 年金開始後用 (男/女)
# col 10-11: 第三分野標準2007 (男/女)
# col 12-13: 標準1996 死亡保険用 (男/女)
# col 14-15: 標準1996 年金開始後用 (男/女)
COLUMN_LAYOUT: list[tuple[str, str, int, int]] = [
    # (table_name, category, col_male, col_female)
    ("標準2018", "死亡保険用", 2, 3),
    ("第三分野2018", "第三分野", 4, 5),
    ("標準2007", "死亡保険用", 6, 7),
    ("標準2007", "年金開始後用", 8, 9),
    ("第三分野2007", "第三分野", 10, 11),
    ("標準1996", "死亡保険用", 12, 13),
    ("標準1996", "年金開始後用", 14, 15),
]


def load_standard_life_tables() -> pd.DataFrame:
    """Excel を tidy 形式に変換 (age, sex, table_name, category, qx)."""
    df_raw = pd.read_excel(XLSX_PATH, header=None)
    # ヘッダ行をスキップし、年齢列が整数であれば採用
    rows = []
    for _, r in df_raw.iterrows():
        age = pd.to_numeric(r.iloc[1], errors="coerce")
        if pd.isna(age):
            continue
        age_i = int(age)
        for table_name, category, cm, cf in COLUMN_LAYOUT:
            for sex_code, col in ((1, cm), (2, cf)):
                qx = pd.to_numeric(r.iloc[col], errors="coerce")
                if pd.isna(qx):
                    continue
                rows.append(
                    {
                        "age": age_i,
                        "sex": sex_code,
                        "table_name": table_name,
                        "category": category,
                        "qx": float(qx),
                    }
                )
    return pd.DataFrame(rows)


def summarise_tables(std: pd.DataFrame) -> pd.DataFrame:
    """テーブル×カテゴリ×性別の年齢カバレッジ・死亡率レンジのサマリ."""
    grp = std.groupby(["table_name", "category", "sex"])
    return grp.agg(
        age_min=("age", "min"),
        age_max=("age", "max"),
        n_rows=("age", "count"),
        qx_min=("qx", "min"),
        qx_max=("qx", "max"),
        qx_mean=("qx", "mean"),
    ).reset_index()


def load_population_mortality() -> pd.DataFrame:
    """DB の population_incidence (mortality) を取得."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"DB not found: {DB_PATH}")
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query(
            """
            SELECT disease_id, sex, age_low, age_high, year,
                   incidence_rate_annual AS pop_qx,
                   incidence_rate_per_100k AS pop_qx_100k
              FROM population_incidence
             WHERE rate_type = 'mortality'
               AND sex IN (1, 2)
            """,
            conn,
        )
    return df


def attach_pop_to_std(
    std: pd.DataFrame, pop: pd.DataFrame, *, year: int, disease_id: str
) -> pd.DataFrame:
    """標準生命表の各 age を population (指定 year, disease_id) と突合する.

    population 側は年齢階級 [age_low, age_high] を持つため、
    std.age が階級に含まれる行を 1 対 1 で結合。
    """
    pop_f = pop[(pop["year"] == year) & (pop["disease_id"] == disease_id)].copy()
    if pop_f.empty:
        return pd.DataFrame()

    merged_rows = []
    for _, r in std.iterrows():
        age = r["age"]
        sex = r["sex"]
        cand = pop_f[
            (pop_f["sex"] == sex)
            & (pop_f["age_low"] <= age)
            & (pop_f["age_high"] >= age)
        ]
        if cand.empty:
            continue
        pop_qx = float(cand["pop_qx"].mean())
        merged_rows.append(
            {
                **r.to_dict(),
                "pop_qx": pop_qx,
                "ratio_pop_over_std": pop_qx / r["qx"] if r["qx"] else None,
            }
        )
    return pd.DataFrame(merged_rows)


def band_summary(merged: pd.DataFrame, *, band: int = 10) -> pd.DataFrame:
    """10 歳帯での比率平均・件数サマリ."""
    if merged.empty:
        return merged
    merged = merged.copy()
    merged["age_band"] = (merged["age"] // band) * band
    g = merged.groupby(["table_name", "category", "sex", "age_band"])
    return g.agg(
        n=("age", "count"),
        qx_std_avg=("qx", "mean"),
        qx_pop_avg=("pop_qx", "mean"),
        ratio_avg=("ratio_pop_over_std", "mean"),
    ).reset_index()


def main() -> int:
    print("=" * 72)
    print(f" 標準生命表ファイル : {XLSX_PATH}")
    print(f" DB                 : {DB_PATH}")
    print("=" * 72)

    if not XLSX_PATH.exists():
        print(
            f"\n[abort] 標準生命表ファイルが見つかりません: {XLSX_PATH}\n"
            "        本再現環境には同梱されていません (README §2)。\n"
            "        日本アクチュアリー会の標準生命表 Excel を上記パスに配置してから"
            "再実行してください。"
        )
        return 1

    # ------------------------------------------------------------------
    # 1. 標準生命表を tidy 形式で読み込み
    # ------------------------------------------------------------------
    std = load_standard_life_tables()
    print(f"\n[1] 標準生命表 (tidy) 行数 = {len(std):,}")
    std_summary = summarise_tables(std)
    print("\n[1a] テーブル別サマリ (sex 1=男 / 2=女)")
    print(std_summary.to_string(index=False))

    std_csv = OUT_DIR / "standard_life_table_tidy.csv"
    std.to_csv(std_csv, index=False, encoding="utf-8-sig")
    print(f"\n  → {std_csv}")

    # ------------------------------------------------------------------
    # 2. DB の人口死亡率を取得
    # ------------------------------------------------------------------
    pop = load_population_mortality()
    print(f"\n[2] population_incidence (mortality) 行数 = {len(pop):,}")
    if pop.empty:
        print("  * mortality データが DB に無いため突合をスキップ")
        return 0

    pop_summary = (
        pop.groupby(["disease_id", "year"])
        .size()
        .reset_index(name="rows")
        .sort_values(["disease_id", "year"])
    )
    print(f"  * disease_id × year ユニーク = {len(pop_summary)}")
    print(pop_summary.head(20).to_string(index=False))

    # ------------------------------------------------------------------
    # 3. 突合 (1): 全死因 disease_id='total' と突合
    # ------------------------------------------------------------------
    available = list(pop["disease_id"].unique())
    if "total" in available:
        disease_id = "total"
    elif any("all" in str(d).lower() for d in available):
        disease_id = next(d for d in available if "all" in str(d).lower())
    else:
        disease_id = available[0]
    latest_year = int(pop[pop["disease_id"] == disease_id]["year"].max())
    print(
        f"\n[3] 突合条件: disease_id = '{disease_id}' (全死因) / year = {latest_year}"
    )

    merged = attach_pop_to_std(std, pop, year=latest_year, disease_id=disease_id)
    print(f"  * 結合行数 = {len(merged):,}")

    if merged.empty:
        return 0

    # 10 歳帯集計
    band = band_summary(merged, band=10)
    print("\n[4] 10 歳帯での比率 (ratio = population_total / standard)")
    print(band.to_string(index=False, float_format=lambda x: f"{x:.4f}"))

    band_csv = OUT_DIR / "standard_vs_population_band10.csv"
    band.to_csv(band_csv, index=False, encoding="utf-8-sig")
    merged_csv = OUT_DIR / "standard_vs_population_detail.csv"
    merged.to_csv(merged_csv, index=False, encoding="utf-8-sig")
    print(f"\n  → {band_csv}")
    print(f"  → {merged_csv}")

    # ------------------------------------------------------------------
    # 5. 妥当性チェック (期待される符号)
    # ------------------------------------------------------------------
    print("\n[5] 妥当性チェック (全死因ベース / 期待符号)")
    check_rows = []
    for (table_name, category), g in merged.groupby(["table_name", "category"]):
        ratio_mean = g["ratio_pop_over_std"].mean()
        ratio_med = g["ratio_pop_over_std"].median()
        # 中央年齢帯 (30-70) に限定した比率も見る
        mid = g[(g["age"] >= 30) & (g["age"] <= 70)]
        ratio_mid = mid["ratio_pop_over_std"].mean() if not mid.empty else None
        hint = _expectation_hint(category, ratio_mid if ratio_mid else ratio_mean)
        check_rows.append(
            {
                "table_name": table_name,
                "category": category,
                "ratio_all_mean": ratio_mean,
                "ratio_all_median": ratio_med,
                "ratio_30_70_mean": ratio_mid,
                "judgement": hint,
            }
        )
        print(
            f"  - {table_name:12s} {category:12s} : "
            f"all mean = {ratio_mean:5.3f}  "
            f"30-70 mean = {ratio_mid:5.3f}  {hint}"
        )
    pd.DataFrame(check_rows).to_csv(
        OUT_DIR / "standard_vs_population_judgement.csv",
        index=False,
        encoding="utf-8-sig",
    )

    # ------------------------------------------------------------------
    # 6. 疾病別寄与: 標準2018 死亡保険用 男性 40-50 代での疾病内訳
    # ------------------------------------------------------------------
    print("\n[6] 疾病別内訳 (標準2018 死亡保険用 男性 40-59 歳)")
    ref = std[
        (std["table_name"] == "標準2018")
        & (std["category"] == "死亡保険用")
        & (std["sex"] == 1)
        & (std["age"].between(40, 59))
    ][["age", "qx"]].rename(columns={"qx": "std_qx"})

    rows = []
    for did in available:
        df_d = pop[(pop["disease_id"] == did) & (pop["year"] == latest_year) & (pop["sex"] == 1)]
        if df_d.empty:
            continue
        for _, r in ref.iterrows():
            cand = df_d[(df_d["age_low"] <= r["age"]) & (df_d["age_high"] >= r["age"])]
            if cand.empty:
                continue
            rows.append(
                {
                    "age": r["age"],
                    "std_qx": r["std_qx"],
                    "disease_id": did,
                    "pop_qx": float(cand["pop_qx"].mean()),
                }
            )
    bd = pd.DataFrame(rows)
    if not bd.empty:
        pivot = bd.pivot_table(
            index="age",
            columns="disease_id",
            values="pop_qx",
            aggfunc="mean",
        )
        pivot["std_qx"] = ref.set_index("age")["std_qx"]
        pivot["sum_diseases"] = pivot.drop(
            columns=[c for c in pivot.columns if c in ("std_qx", "total")]
        ).sum(axis=1)
        pivot = pivot.reset_index()
        # 各疾病が std_qx に占める割合
        for did in available:
            if did in pivot.columns and did != "total":
                pivot[f"{did}_share_vs_std"] = pivot[did] / pivot["std_qx"]
        print(pivot.round(6).to_string(index=False))
        pivot.to_csv(
            OUT_DIR / "disease_breakdown_std2018_male_40_59.csv",
            index=False,
            encoding="utf-8-sig",
        )

    return 0


def _expectation_hint(category: str, ratio: float) -> str:
    """保険数理的な期待符号の解説文."""
    if category == "死亡保険用":
        if ratio < 1.0:
            return "[OK] 安全割増: pop < std (死亡保険用は population より高い)"
        else:
            return "[CHECK] 死亡保険用は通常 pop < std が期待される"
    if category == "年金開始後用":
        if ratio > 1.0:
            return "[OK] 長生き前提: pop > std (年金は長生きに備え低め)"
        else:
            return "[CHECK] 年金開始後用は通常 pop > std が期待される"
    if category == "第三分野":
        return "[REF] 罹患率概念のため死亡率との直接比較は参考値"
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
