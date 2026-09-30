"""疾病発生率パネル (incidence_panel) の統合ビルダ.

以下のサブビルダを順に呼び出し、結果を縦結合して
``data/processed/incidence_panel.parquet / .csv`` に書き出す。

    registry       : scripts/build_cancer_registry_panel.py (がん登録)
    initial_visit  : scripts/build_initial_visit_panel.py   (Z70/Z13)
    discharge      : scripts/build_discharge_panel.py       (Z10+LOS)
    mortality      : scripts/build_mortality_incidence_panel.py (5-15)

各サブビルダは失敗/データ欠で空 DataFrame を返してもパイプラインを止めない。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

# scripts/ 配下のモジュールを import できるよう調整
sys.path.insert(0, str(Path(__file__).resolve().parent))

from panel_helpers import (  # noqa: E402
    INCIDENCE_PANEL_COLUMNS,
    PROCESSED,
    conform_incidence_panel,
    empty_incidence_panel,
)


def _safe_build(name: str, builder) -> pd.DataFrame:
    try:
        df = builder()
    except Exception as exc:  # noqa: BLE001
        print(f"[{name}] ERROR: {exc}")
        return empty_incidence_panel()
    if df is None or df.empty:
        print(f"[{name}] 0 rows (skipped or empty)")
        return empty_incidence_panel()
    print(f"[{name}] {len(df)} rows")
    return conform_incidence_panel(df)


def build_all() -> pd.DataFrame:
    parts: list[pd.DataFrame] = []

    # (1) mortality (基盤として常に使える)
    try:
        from build_mortality_incidence_panel import build as build_mortality

        parts.append(_safe_build("mortality", build_mortality))
    except ImportError as exc:
        print(f"[mortality] import error: {exc}")

    # (2) registry (P3 以降)
    try:
        from build_cancer_registry_panel import build as build_registry

        parts.append(_safe_build("registry", build_registry))
    except ImportError as exc:
        print(f"[registry] not yet implemented ({exc})")

    # (3) initial_visit (P2)
    try:
        from build_initial_visit_panel import build as build_initial

        parts.append(_safe_build("initial_visit", build_initial))
    except ImportError as exc:
        print(f"[initial_visit] not yet implemented ({exc})")

    # (4) discharge (P4)
    try:
        from build_discharge_panel import build as build_discharge

        parts.append(_safe_build("discharge", build_discharge))
    except ImportError as exc:
        print(f"[discharge] not yet implemented ({exc})")

    parts = [p for p in parts if not p.empty]
    if not parts:
        return empty_incidence_panel()

    merged = pd.concat(parts, ignore_index=True, sort=False)
    merged = conform_incidence_panel(merged)

    # 型整理
    for col in ("age_low", "age_high", "year", "sex_code"):
        merged[col] = pd.to_numeric(merged[col], errors="coerce").astype("Int64")
    for col in (
        "incidence_rate_annual",
        "incidence_rate_per_100k",
        "numerator_count",
        "population_thousand",
    ):
        merged[col] = pd.to_numeric(merged[col], errors="coerce")

    # 主キー重複チェック (SQL population_incidence PK に対応)
    key = ["disease_norm", "sex", "age_code", "year", "section", "rate_type"]
    dup = merged.duplicated(subset=key, keep=False)
    if dup.any():
        n = int(dup.sum())
        print(f"[warn] duplicated keys: {n} rows (first kept)")
        merged = merged.drop_duplicates(subset=key, keep="first")

    sort_cols = ["rate_type", "disease_id", "disease_norm", "year", "sex", "age_low"]
    merged = merged.sort_values(sort_cols).reset_index(drop=True)
    return merged


def _lost_rate_types(existing_csv: Path, df: pd.DataFrame) -> list[str]:
    """既存パネルにあって新パネルに無い rate_type を返す."""
    try:
        old = pd.read_csv(existing_csv, usecols=["rate_type"])
    except Exception:  # noqa: BLE001
        return []
    new_types = set(df["rate_type"].dropna()) if "rate_type" in df.columns else set()
    return sorted(set(old["rate_type"].dropna()) - new_types)


def main() -> int:
    parser = argparse.ArgumentParser(description="疾病発生率パネル統合ビルダ")
    parser.add_argument(
        "--outdir",
        default=str(PROCESSED),
        help=f"出力ディレクトリ (default: {PROCESSED})",
    )
    parser.add_argument(
        "--name",
        default="incidence_panel",
        help="出力ベース名 (default: incidence_panel)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="既存パネルより rate_type が減っていても上書きする",
    )
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    df = build_all()

    csv_path = outdir / f"{args.name}.csv"
    parquet_path = outdir / f"{args.name}.parquet"

    # 生データ未同梱の環境ではサブビルダが空を返すため、そのまま書くと
    # 同梱済みパネルを縮退版で上書きしてしまう。既存より rate_type が
    # 減る場合は書き込まず中止する (README §2 参照)。
    if csv_path.exists() and not args.force:
        lost = _lost_rate_types(csv_path, df)
        if lost:
            print(
                f"[abort] 既存パネル {csv_path} にある rate_type が再構築結果から"
                f"欠落しています: {', '.join(lost)}\n"
                "        入力の e-Stat 生データ (data/RowData/estat_processed/) が"
                "同梱されていない可能性があります。\n"
                "        同梱パネルを保護するため書き込みを中止しました。"
                "意図的に上書きする場合は --force を付けてください。"
            )
            return 1

    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"[build_incidence_panel] CSV saved: {csv_path} ({len(df)} rows)")
    try:
        df.to_parquet(parquet_path, index=False)
        print(f"[build_incidence_panel] Parquet saved: {parquet_path}")
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] parquet 書き込み失敗: {exc}")

    # サマリ
    if not df.empty:
        print("\n[summary] rate_type × disease_id:")
        pivot = (
            df.groupby(["rate_type", "disease_id"], dropna=False)
            .size()
            .unstack(fill_value=0)
        )
        print(pivot.to_string())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
