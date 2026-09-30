"""CSV → SQLite の ETL (取込) 処理.

本モジュールは人口ベース疾病発生率パネル (``incidence_panel.csv`` /
``rider_disease_map.csv``) の一括ロードに特化している。

本再現環境では契約データ (実績保有・異動データ) を扱わないため、
経験率 (A/E) 分析系の取込機能は同梱していない。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

import pandas as pd

from .db import PROJECT_ROOT, connect

# 人口ベース疾病発生率 (incidence_panel, rider_disease_map) の追加ロード順.
INCIDENCE_LOAD_ORDER: list[tuple[str, str]] = [
    ("population_incidence", "incidence_panel.csv"),
    ("rider_disease_map", "rider_disease_map.csv"),
]


def _resolve(path: str | Path) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p


def load_incidence_panel(
    db_path: str | Path,
    data_dir: str | Path,
    *,
    verbose: bool = True,
) -> dict[str, int]:
    """人口ベース発生率パネル (incidence_panel.csv 等) を DB にロードする.

    Args:
        db_path: SQLite ファイル
        data_dir: CSV 探索先 (通常は ``data/processed``)
    """
    data_dir_path = _resolve(data_dir)
    if not data_dir_path.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir_path}")

    conn = connect(db_path)
    counts: dict[str, int] = {}
    try:
        for table, csv_name in INCIDENCE_LOAD_ORDER:
            csv_path = data_dir_path / csv_name
            if not csv_path.exists():
                if verbose:
                    print(f"  [skip] {table}: {csv_path.name} が存在しません")
                counts[table] = 0
                continue

            # rider_disease_map ロード前に、rider_def へ rider_code を自動補完
            # (rider_def は表示用マスタで FK 制約は無いが、analyze 結果の
            #  rider_name を引けるようにしておく)
            if table == "rider_disease_map":
                added = _upsert_rider_def_from_map(conn, csv_path)
                if verbose and added:
                    print(f"  [auto] rider_def: {added} 件の rider_code を補完")

            n = _load_incidence_csv_to_table(conn, table, csv_path)
            counts[table] = n
            if verbose:
                print(f"  [load] {table}: {n} 行 (from {csv_path.name})")
        conn.commit()
    finally:
        conn.close()
    return counts


def _upsert_rider_def_from_map(conn: sqlite3.Connection, csv_path: Path) -> int:
    """``rider_disease_map.csv`` の ``rider_code`` を ``rider_def`` に upsert.

    既存行は上書きせず、未登録の rider_code のみ最低限の情報で挿入する。
    """
    df = pd.read_csv(csv_path, encoding="utf-8-sig", keep_default_na=False, na_values=[""])
    if df.empty or "rider_code" not in df.columns:
        return 0

    codes = sorted({str(c).strip() for c in df["rider_code"].dropna().tolist() if str(c).strip()})
    if not codes:
        return 0

    existing = {
        row[0]
        for row in conn.execute("SELECT rider_code FROM rider_def").fetchall()
    }
    missing = [c for c in codes if c not in existing]
    if not missing:
        return 0

    conn.executemany(
        "INSERT INTO rider_def (rider_code, rider_name, rider_category, display_order) "
        "VALUES (?, ?, ?, ?)",
        [(c, c, "auto_generated", i) for i, c in enumerate(missing)],
    )
    return len(missing)


def _load_incidence_csv_to_table(
    conn: sqlite3.Connection,
    table: str,
    csv_path: Path,
) -> int:
    """incidence_panel.csv → population_incidence へのマッピング付きロード.

    incidence_panel.csv のカラム名は population_incidence のカラム名と
    基本的に一致するが、sex は文字列 ('total'/'male'/'female') で入っている
    ため、sex_code 列を sex に置き換える。
    """
    df = pd.read_csv(
        csv_path, encoding="utf-8-sig", keep_default_na=False, na_values=[""]
    )

    if df.empty:
        return 0

    if table == "population_incidence":
        if "sex_code" in df.columns:
            df["sex"] = (
                pd.to_numeric(df["sex_code"], errors="coerce")
                .fillna(0)
                .astype(int)
            )
        elif "sex" in df.columns and df["sex"].dtype == object:
            mapping = {"total": 0, "male": 1, "female": 2}
            df["sex"] = df["sex"].map(mapping).fillna(0).astype(int)

        pk_cols = ["disease_norm", "sex", "age_code", "year", "section", "rate_type"]
        pk_cols = [c for c in pk_cols if c in df.columns]
        df = df.dropna(subset=pk_cols)

        keep = [
            "disease_id",
            "disease_norm",
            "icd10",
            "sex",
            "age_code",
            "age_low",
            "age_high",
            "year",
            "section",
            "rate_type",
            "incidence_rate_annual",
            "incidence_rate_per_100k",
            "numerator_count",
            "population_thousand",
            "source_table",
            "quality_flag",
            "method_note",
        ]
        df = df[[c for c in keep if c in df.columns]]

        for c in ("sex", "age_low", "age_high", "year"):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        for c in (
            "incidence_rate_annual",
            "incidence_rate_per_100k",
            "numerator_count",
            "population_thousand",
        ):
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")

    conn.execute(f"DELETE FROM {table}")
    cols = df.columns.tolist()
    placeholders = ",".join(["?"] * len(cols))
    col_list = ",".join(f'"{c}"' for c in cols)
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"

    def _cell(v):
        if v is None:
            return None
        if isinstance(v, float) and pd.isna(v):
            return None
        return v

    rows = [tuple(_cell(v) for v in row) for row in df.itertuples(index=False)]
    conn.executemany(sql, rows)
    return len(rows)


def show_summary(db_path: str | Path, tables: Iterable[str] | None = None) -> None:
    """各テーブルの行数を表示."""
    conn = connect(db_path)
    try:
        if tables is None:
            tables = [
                "parameters",
                "rider_def",
                "rider_disease_map",
                "population_incidence",
            ]
        print("Table summary:")
        for t in tables:
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                print(f"  {t:<22} {n:>8} rows")
            except sqlite3.OperationalError:
                print(f"  {t:<22}        - (not exists)")

        # Scale BB 系テーブルは任意 (存在しなければ黙って skip)
        for t in (
            "scalebb_run",
            "scalebb_improvement",
            "scalebb_cohort_effect",
            "scalebb_projection",
            "predicted_rate_generational",
        ):
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                print(f"  {t:<22} {n:>8} rows")
            except sqlite3.OperationalError:
                pass
    finally:
        conn.close()


def build_population_benchmark(
    conn: sqlite3.Connection,
    *,
    disease_ids: list[str] | None = None,
    rate_types: list[str] | None = None,
    year: int | None = None,
    sex: int | None = None,
) -> pd.DataFrame:
    """population_incidence から人口ベンチマーク発生率を取得する.

    Args:
        disease_ids: 絞り込みたい disease_id (例: ['cancer', 'heart_disease'])
        rate_types:  絞り込みたい rate_type (例: ['registry', 'initial_visit'])
        year:        年で絞り込み
        sex:         0=総数/1=男/2=女 で絞り込み

    Returns:
        population_incidence テーブルの DataFrame (指定条件で絞り込み済)
    """
    clauses: list[str] = []
    params: list = []
    if disease_ids:
        placeholders = ",".join(["?"] * len(disease_ids))
        clauses.append(f"disease_id IN ({placeholders})")
        params.extend(disease_ids)
    if rate_types:
        placeholders = ",".join(["?"] * len(rate_types))
        clauses.append(f"rate_type IN ({placeholders})")
        params.extend(rate_types)
    if year is not None:
        clauses.append("year = ?")
        params.append(year)
    if sex is not None:
        clauses.append("sex = ?")
        params.append(sex)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT
            disease_id, disease_norm, icd10, sex, age_code, age_low, age_high,
            year, section, rate_type,
            incidence_rate_annual, incidence_rate_per_100k,
            numerator_count, population_thousand,
            source_table, quality_flag, method_note
        FROM population_incidence
        {where}
        ORDER BY disease_id, rate_type, year, sex, age_low
    """
    return pd.read_sql_query(sql, conn, params=tuple(params))
