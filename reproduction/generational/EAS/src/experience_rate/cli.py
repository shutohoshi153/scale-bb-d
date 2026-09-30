"""コマンドラインインターフェース.

使用例::

    python -m experience_rate init --drop
    python -m experience_rate scalebb-apc-fit --source mortality --sex male

    # 疾病発生率 (人口ベンチマーク) 系
    python -m experience_rate build-incidence
    python -m experience_rate load-incidence --data-dir data/processed
    python -m experience_rate export-incidence --output output/incidence.csv
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd

from tabulate import tabulate

from . import db, etl, scalebb, scalebb_apc, scalebb_gen


def _make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="experience_rate",
        description="経験率分析システム (SQLite + Python)",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="設定ファイルパス (default: config.yaml)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = sub.add_parser("init", help="SQLite DB を初期化 (スキーマ構築)")
    p_init.add_argument(
        "--drop",
        action="store_true",
        help="既存の DB ファイルを削除してから再構築",
    )

    # summary
    sub.add_parser("summary", help="各テーブルの行数を表示")

    # -------------------------------------------------------------------------
    # 疾病発生率 (人口ベンチマーク) 系サブコマンド
    # -------------------------------------------------------------------------
    sub.add_parser(
        "build-incidence",
        help="scripts/build_incidence_panel.py を実行して incidence_panel を生成",
    )

    p_load_inc = sub.add_parser(
        "load-incidence",
        help="incidence_panel.csv と rider_disease_map.csv を DB にロード",
    )
    p_load_inc.add_argument(
        "--data-dir",
        default=None,
        help="CSV 格納ディレクトリ (省略時は config.paths.processed)",
    )

    p_exp_inc = sub.add_parser(
        "export-incidence",
        help="population_incidence から指定条件で CSV 書き出し",
    )
    p_exp_inc.add_argument("--output", required=True, help="出力 CSV パス")
    p_exp_inc.add_argument(
        "--rate-type",
        nargs="*",
        default=None,
        help="絞り込む rate_type (例: registry initial_visit)",
    )
    p_exp_inc.add_argument(
        "--disease", nargs="*", default=None, help="絞り込む disease_id"
    )
    p_exp_inc.add_argument("--year", type=int, default=None, help="絞り込む年")
    p_exp_inc.add_argument(
        "--sex", type=int, choices=[0, 1, 2], default=None, help="0=総数/1=男/2=女"
    )

    # -------------------------------------------------------------------------
    # Scale BB 拡張モデル (疾病発生率/死亡率への応用) 系サブコマンド
    # -------------------------------------------------------------------------
    p_sb_fit = sub.add_parser(
        "scalebb-fit",
        help="Scale BB Phase 1 (2D 平滑化 + 改善率抽出) を実行し DB にロード",
    )
    p_sb_fit.add_argument(
        "--source",
        choices=["mortality", "age_period"],
        default="mortality",
        help="入力パネル種別 (mortality_apc / age_period)",
    )
    p_sb_fit.add_argument(
        "--disease",
        nargs="*",
        default=None,
        help="mortality 時の対象 disease_id",
    )
    p_sb_fit.add_argument("--sex", default="total", choices=["total", "male", "female"])
    p_sb_fit.add_argument(
        "--section",
        default="total",
        choices=["total", "inpatient", "outpatient"],
    )
    p_sb_fit.add_argument("--age-min", type=int, default=20)
    p_sb_fit.add_argument("--age-max", type=int, default=89)
    p_sb_fit.add_argument("--year-min", type=int, default=None)
    p_sb_fit.add_argument("--year-max", type=int, default=None)
    p_sb_fit.add_argument("--lam-row", type=float, default=40.0)
    p_sb_fit.add_argument("--lam-col", type=float, default=40.0)
    p_sb_fit.add_argument(
        "--output",
        default=None,
        help="fit 結果 parquet パス (省略時: <repo>/data/processed/scalebb_fit.parquet)",
    )
    p_sb_fit.add_argument("--run-id", default=None)
    p_sb_fit.add_argument(
        "--no-load", action="store_true", help="DB にロードしない (CSV/parquet のみ)"
    )

    p_sb_proj = sub.add_parser(
        "scalebb-project",
        help="Scale BB Phase 2 (長期率ブレンド + 将来投影) を実行し DB にロード",
    )
    p_sb_proj.add_argument(
        "--fit",
        required=True,
        help="scalebb-fit で生成した parquet/CSV ファイル",
    )
    p_sb_proj.add_argument("--long-term-rate", type=float, default=0.01)
    p_sb_proj.add_argument("--convergence-year", type=int, default=2035)
    p_sb_proj.add_argument("--horizon", type=int, default=2050)
    p_sb_proj.add_argument("--last-observed-year", type=int, default=None)
    p_sb_proj.add_argument(
        "--output",
        default=None,
        help="投影結果 parquet パス (省略時: <repo>/data/processed/scalebb_projection.parquet)",
    )
    p_sb_proj.add_argument("--run-id", default=None)
    p_sb_proj.add_argument("--no-load", action="store_true")

    p_sb_heat = sub.add_parser(
        "scalebb-heatmap",
        help="Scale BB スタイルのヒートマップ/投影図 (PNG) を生成",
    )
    p_sb_heat.add_argument(
        "--source", choices=["mortality", "age_period"], default="mortality"
    )
    p_sb_heat.add_argument("--disease", nargs="*", default=None)
    p_sb_heat.add_argument("--sex", default="total", choices=["total", "male", "female"])
    p_sb_heat.add_argument(
        "--section", default="total", choices=["total", "inpatient", "outpatient"]
    )
    p_sb_heat.add_argument("--age-min", type=int, default=20)
    p_sb_heat.add_argument("--age-max", type=int, default=89)
    p_sb_heat.add_argument("--year-min", type=int, default=None)
    p_sb_heat.add_argument("--year-max", type=int, default=None)
    p_sb_heat.add_argument("--long-term-rate", type=float, default=0.01)
    p_sb_heat.add_argument("--convergence-year", type=int, default=2035)
    p_sb_heat.add_argument("--horizon", type=int, default=2050)
    p_sb_heat.add_argument(
        "--output-dir",
        default="output/scalebb_figures",
        help="図の出力ディレクトリ (EAS/output/scalebb_figures)",
    )

    p_sb_runs = sub.add_parser(
        "scalebb-runs", help="scalebb_run テーブルの履歴一覧"
    )
    p_sb_runs.add_argument("--last", type=int, default=20)

    p_sb_gen = sub.add_parser(
        "scalebb-gen-table",
        help="Generational Projection で発行年別 1D 予定発生率テーブルを生成",
    )
    p_sb_gen.add_argument(
        "--run-id",
        required=True,
        help="対象の scalebb_projection run_id (scalebb-runs で確認)",
    )
    p_sb_gen.add_argument(
        "--issue-years",
        nargs="+",
        type=int,
        default=None,
        help="発行年のリスト (省略時は config.scalebb_presets.generational を参照)",
    )
    p_sb_gen.add_argument(
        "--issue-age",
        type=int,
        default=None,
        help="契約時年齢 (省略時 preset、最終デフォルト 0)",
    )
    p_sb_gen.add_argument("--age-min", type=int, default=None)
    p_sb_gen.add_argument("--age-max", type=int, default=None)
    p_sb_gen.add_argument(
        "--disease",
        nargs="*",
        default=None,
        help="対象 disease_id (省略時は run_id 内全疾病)",
    )
    p_sb_gen.add_argument(
        "--sex",
        nargs="*",
        default=None,
        help="対象 sex 'total' / 'male' / 'female' (複数指定可)",
    )
    p_sb_gen.add_argument(
        "--section",
        default="total",
        choices=["total", "inpatient", "outpatient"],
    )
    p_sb_gen.add_argument(
        "--interpolate-age",
        action="store_true",
        help="5 歳ビンを単年齢に補間 (log 空間の線形補間)",
    )
    p_sb_gen.add_argument(
        "--interpolation-method",
        default=None,
        choices=["log_linear", "linear", "log_pchip"],
        help="補間方法 (default: preset または log_linear)",
    )
    p_sb_gen.add_argument(
        "--use-preset",
        action="store_true",
        help="config.yaml の scalebb_presets.generational を既定値として適用",
    )
    p_sb_gen.add_argument(
        "--output-dir",
        default=None,
        help="CSV 出力ディレクトリ (省略時: <repo>/data/processed/predicted_rate_tables)",
    )
    p_sb_gen.add_argument(
        "--no-load",
        action="store_true",
        help="predicted_rate_generational テーブルに書き込まず CSV のみ生成",
    )

    # --- Scale BB APC (Age-Period-Cohort) 拡張 -------------------------------
    p_sb_apc_fit = sub.add_parser(
        "scalebb-apc-fit",
        help="APC 拡張 (対角罰則 + γ コホート効果) を実行し DB にロード",
    )
    p_sb_apc_fit.add_argument(
        "--source",
        choices=["mortality", "age_period"],
        default="mortality",
    )
    p_sb_apc_fit.add_argument("--disease", nargs="*", default=None)
    p_sb_apc_fit.add_argument(
        "--sex", default="total", choices=["total", "male", "female"]
    )
    p_sb_apc_fit.add_argument(
        "--section", default="total", choices=["total", "inpatient", "outpatient"]
    )
    p_sb_apc_fit.add_argument("--age-min", type=int, default=None)
    p_sb_apc_fit.add_argument("--age-max", type=int, default=None)
    p_sb_apc_fit.add_argument("--year-min", type=int, default=None)
    p_sb_apc_fit.add_argument("--year-max", type=int, default=None)
    p_sb_apc_fit.add_argument("--lam-row", type=float, default=None)
    p_sb_apc_fit.add_argument("--lam-col", type=float, default=None)
    p_sb_apc_fit.add_argument("--lam-cohort", type=float, default=None)
    p_sb_apc_fit.add_argument("--long-term-rate", type=float, default=None)
    p_sb_apc_fit.add_argument("--convergence-year", type=int, default=None)
    p_sb_apc_fit.add_argument("--horizon-year", type=int, default=None)
    p_sb_apc_fit.add_argument(
        "--covid-mode",
        default=None,
        choices=["weight_down", "dummy", "none"],
    )
    p_sb_apc_fit.add_argument("--covid-weight", type=float, default=None)
    p_sb_apc_fit.add_argument(
        "--covid-years", nargs="*", type=int, default=None
    )
    p_sb_apc_fit.add_argument(
        "--use-preset",
        action="store_true",
        help="config.yaml の scalebb_presets を既定値として適用 (推奨)",
    )
    p_sb_apc_fit.add_argument("--output", default=None)
    p_sb_apc_fit.add_argument("--run-id", default=None)
    p_sb_apc_fit.add_argument("--no-load", action="store_true")

    p_sb_apc_proj = sub.add_parser(
        "scalebb-apc-project",
        help="APC fit 結果を将来へ投影し DB にロード",
    )
    p_sb_apc_proj.add_argument("--fit", required=True)
    p_sb_apc_proj.add_argument("--long-term-rate", type=float, default=None)
    p_sb_apc_proj.add_argument("--convergence-year", type=int, default=None)
    p_sb_apc_proj.add_argument("--horizon-year", type=int, default=None)
    p_sb_apc_proj.add_argument("--last-observed-year", type=int, default=None)
    p_sb_apc_proj.add_argument(
        "--cohort-extrapolation",
        default=None,
        choices=["flat", "last_drift"],
    )
    p_sb_apc_proj.add_argument(
        "--use-preset",
        action="store_true",
        help="config.yaml の scalebb_presets を既定値として適用",
    )
    p_sb_apc_proj.add_argument("--output", default=None)
    p_sb_apc_proj.add_argument("--run-id", default=None)
    p_sb_apc_proj.add_argument("--no-load", action="store_true")

    p_sb_load = sub.add_parser(
        "scalebb-load",
        help="既存の scalebb fit/projection CSV を DB にロード",
    )
    p_sb_load.add_argument(
        "--kind", choices=["fit", "projection"], required=True
    )
    p_sb_load.add_argument("--file", required=True, help="fit/projection parquet or CSV")
    p_sb_load.add_argument(
        "--meta", default=None, help="*.meta.json (省略時は --file の拡張子を差し替えて自動探索)"
    )

    return parser


def _resolve_db_path(config: dict) -> Path:
    return Path(config["database"]["path"])


def cmd_init(args, config) -> int:
    db_path = _resolve_db_path(config)
    db.initialize(db_path, drop_existing=args.drop)
    print(f"[init] Database initialized: {db_path}")
    _upsert_parameters(db_path, config)
    return 0


def _upsert_parameters(db_path: Path, config: dict) -> None:
    """config.yaml の parameters を DB にアップサート."""
    params = config["parameters"]
    conn = db.connect(db_path)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO parameters (
                id, observation_year_end_month, fiscal_year_end_month
            ) VALUES (1, ?, ?)
            """,
            (
                params["observation_year_end_month"],
                params["fiscal_year_end_month"],
            ),
        )
        conn.commit()
    finally:
        conn.close()
    print("[init] config.yaml の parameters を DB に反映")


def cmd_summary(args, config) -> int:
    db_path = _resolve_db_path(config)
    etl.show_summary(db_path)
    return 0


def cmd_build_incidence(args, config) -> int:
    """EAS/scripts/build_incidence_panel.py を呼び出して incidence_panel を生成."""
    import os

    script = db.PROJECT_ROOT / "scripts" / "build_incidence_panel.py"
    if not script.exists():
        print(f"[build-incidence] Script not found: {script}")
        return 1
    print(f"[build-incidence] Running {script.name}")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(db.PROJECT_ROOT),
        env=env,
    )
    return result.returncode


def cmd_load_incidence(args, config) -> int:
    db_path = _resolve_db_path(config)
    data_dir = args.data_dir or config.get("paths", {}).get("processed", "data/processed")
    print(f"[load-incidence] data_dir = {data_dir}")
    counts = etl.load_incidence_panel(db_path, data_dir)
    total = sum(counts.values())
    print(f"[load-incidence] done ({total} rows)")
    return 0


def cmd_export_incidence(args, config) -> int:
    db_path = _resolve_db_path(config)
    conn = db.connect(db_path)
    try:
        df = etl.build_population_benchmark(
            conn,
            disease_ids=args.disease,
            rate_types=args.rate_type,
            year=args.year,
            sex=args.sex,
        )
    finally:
        conn.close()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"[export-incidence] {len(df)} rows → {output_path}")
    return 0


def cmd_scalebb_fit(args, config) -> int:
    db_path = _resolve_db_path(config)
    try:
        result = scalebb.run_fit(
            db_path=db_path,
            source=args.source,
            diseases=args.disease,
            sex=args.sex,
            section=args.section,
            age_min=args.age_min,
            age_max=args.age_max,
            year_min=args.year_min,
            year_max=args.year_max,
            lam_row=args.lam_row,
            lam_col=args.lam_col,
            output_path=args.output,
            run_id=args.run_id,
            load_to_db=not args.no_load,
        )
    except Exception as exc:
        print(f"[scalebb-fit] error: {exc}")
        return 1
    print(
        f"[scalebb-fit] run_id={result['run_id']} "
        f"rows_loaded={result['rows_loaded']} "
        f"output={result['output_file']}"
    )
    return 0


def cmd_scalebb_project(args, config) -> int:
    db_path = _resolve_db_path(config)
    try:
        result = scalebb.run_projection(
            db_path=db_path,
            fit_file=args.fit,
            long_term_rate=args.long_term_rate,
            convergence_year=args.convergence_year,
            horizon=args.horizon,
            last_observed_year=args.last_observed_year,
            output_path=args.output,
            run_id=args.run_id,
            load_to_db=not args.no_load,
        )
    except Exception as exc:
        print(f"[scalebb-project] error: {exc}")
        return 1
    print(
        f"[scalebb-project] run_id={result['run_id']} "
        f"rows_loaded={result['rows_loaded']} "
        f"output={result['output_file']}"
    )
    return 0


def cmd_scalebb_heatmap(args, config) -> int:
    try:
        output_paths = scalebb.run_heatmap(
            output_dir=args.output_dir,
            source=args.source,
            diseases=args.disease,
            sex=args.sex,
            section=args.section,
            age_min=args.age_min,
            age_max=args.age_max,
            year_min=args.year_min,
            year_max=args.year_max,
            long_term_rate=args.long_term_rate,
            convergence_year=args.convergence_year,
            horizon=args.horizon,
        )
    except Exception as exc:
        print(f"[scalebb-heatmap] error: {exc}")
        return 1
    print(f"[scalebb-heatmap] generated {len(output_paths)} PNG files")
    for p in output_paths:
        print(f"  {p}")
    return 0


def cmd_scalebb_runs(args, config) -> int:
    db_path = _resolve_db_path(config)
    conn = db.connect(db_path)
    try:
        df = scalebb.list_runs(conn)
    finally:
        conn.close()
    if df.empty:
        print("[scalebb-runs] (no runs)")
        return 0
    df = df.head(args.last)
    cols = [
        "run_id", "kind", "source_panel", "diseases", "sex",
        "age_min", "age_max", "year_min", "year_max",
        "long_term_rate", "convergence_year", "horizon_year", "created_at",
    ]
    display = df[[c for c in cols if c in df.columns]].copy()
    print(tabulate(display, headers="keys", tablefmt="grid", showindex=False))
    return 0


def cmd_scalebb_gen_table(args, config) -> int:
    db_path = _resolve_db_path(config)

    gen_preset = db.resolve_generational_preset(config) if args.use_preset else {}
    issue_years = args.issue_years or gen_preset.get("issue_years")
    if not issue_years:
        print(
            "[scalebb-gen-table] error: --issue-years 未指定かつ preset 未定義。"
            "--issue-years を指定するか --use-preset を付与してください"
        )
        return 1
    issue_age = (
        args.issue_age if args.issue_age is not None else gen_preset.get("issue_age", 0)
    )
    age_min = (
        args.age_min if args.age_min is not None else gen_preset.get("age_min", 0)
    )
    age_max = (
        args.age_max if args.age_max is not None else gen_preset.get("age_max", 99)
    )
    interpolate_age = args.interpolate_age or bool(
        gen_preset.get("interpolate_age", False)
    )
    interpolation_method = (
        args.interpolation_method
        or gen_preset.get("interpolation_method", "log_linear")
    )

    try:
        result = scalebb_gen.build_generational_tables(
            db_path=db_path,
            run_id=args.run_id,
            issue_years=issue_years,
            issue_age=int(issue_age),
            age_min=int(age_min),
            age_max=int(age_max),
            disease_ids=args.disease,
            sexes=args.sex,
            section=args.section,
            output_dir=args.output_dir,
            load_to_db=not args.no_load,
            interpolate_age=interpolate_age,
            interpolation_method=interpolation_method,
        )
    except Exception as exc:
        print(f"[scalebb-gen-table] error: {exc}")
        return 1
    print(
        f"[scalebb-gen-table] run_id={result['run_id']}\n"
        f"  rows_loaded = {result['rows_loaded']}\n"
        f"  files_written = {len(result['files_written'])}\n"
        f"  output_dir = {result['output_dir']}\n"
        f"  master_csv = {result['master_csv']}\n"
        f"  interpolate_age = {interpolate_age} ({interpolation_method})"
    )
    return 0


def _merge_preset_apc(args, config) -> dict:
    """APC fit 用に preset + CLI 引数をマージ (CLI 優先)."""
    disease = None
    if getattr(args, "disease", None):
        if len(args.disease) == 1:
            disease = args.disease[0]
    sex = getattr(args, "sex", None)
    preset = db.resolve_scalebb_preset(config, disease=disease, sex=sex) if args.use_preset else {}

    def _pick(name: str, default):
        v = getattr(args, name.replace("-", "_"), None)
        if v is not None:
            return v
        if name in preset:
            return preset[name]
        return default

    return {
        "age_min": int(_pick("age_min", 20)),
        "age_max": int(_pick("age_max", 89)),
        "lam_row": float(_pick("lam_row", 40.0)),
        "lam_col": float(_pick("lam_col", 40.0)),
        "lam_cohort": float(_pick("lam_cohort", 40.0)),
        "long_term_rate": float(_pick("long_term_rate", 0.01)),
        "convergence_year": int(_pick("convergence_year", 2035)),
        "horizon_year": int(_pick("horizon_year", 2100)),
        "covid_mode": str(_pick("covid_mode", "dummy")),
        "covid_weight": float(_pick("covid_weight", 0.3)),
        "covid_years": tuple(int(y) for y in _pick("covid_years", (2020, 2021, 2022))),
        "cohort_extrapolation": str(_pick("cohort_extrapolation", "last_drift")),
    }


def cmd_scalebb_apc_fit(args, config) -> int:
    db_path = _resolve_db_path(config)
    p = _merge_preset_apc(args, config)
    try:
        result = scalebb_apc.run_apc_fit(
            db_path=db_path,
            source=args.source,
            diseases=args.disease,
            sex=args.sex,
            section=args.section,
            age_min=p["age_min"],
            age_max=p["age_max"],
            year_min=args.year_min,
            year_max=args.year_max,
            lam_row=p["lam_row"],
            lam_col=p["lam_col"],
            lam_cohort=p["lam_cohort"],
            long_term_rate=p["long_term_rate"],
            convergence_year=p["convergence_year"],
            horizon_year=p["horizon_year"],
            covid_mode=p["covid_mode"],
            covid_weight=p["covid_weight"],
            covid_years=p["covid_years"],
            output_path=args.output,
            run_id=args.run_id,
            load_to_db=not args.no_load,
        )
    except Exception as exc:
        print(f"[scalebb-apc-fit] error: {exc}")
        return 1
    print(
        f"[scalebb-apc-fit] run_id={result['run_id']}\n"
        f"  improvement_rows = {result['rows_loaded']}\n"
        f"  cohort_effect_rows = {result['cohorts_loaded']}\n"
        f"  output = {result['output_file']}\n"
        f"  cohort_file = {result['cohort_file']}"
    )
    return 0


def cmd_scalebb_apc_project(args, config) -> int:
    db_path = _resolve_db_path(config)
    p = _merge_preset_apc(args, config)
    try:
        result = scalebb_apc.run_apc_project(
            db_path=db_path,
            fit_file=args.fit,
            long_term_rate=args.long_term_rate if args.long_term_rate is not None else p["long_term_rate"],
            convergence_year=args.convergence_year if args.convergence_year is not None else p["convergence_year"],
            horizon_year=args.horizon_year if args.horizon_year is not None else p["horizon_year"],
            last_observed_year=args.last_observed_year,
            cohort_extrapolation=args.cohort_extrapolation or p["cohort_extrapolation"],
            output_path=args.output,
            run_id=args.run_id,
            load_to_db=not args.no_load,
        )
    except Exception as exc:
        print(f"[scalebb-apc-project] error: {exc}")
        return 1
    print(
        f"[scalebb-apc-project] run_id={result['run_id']}\n"
        f"  rows_loaded = {result['rows_loaded']}\n"
        f"  output = {result['output_file']}"
    )
    return 0


def cmd_scalebb_load(args, config) -> int:
    db_path = _resolve_db_path(config)
    meta_path = args.meta
    if meta_path is None:
        p = Path(args.file)
        candidate = p.with_suffix(".meta.json")
        if candidate.exists():
            meta_path = str(candidate)
    try:
        if args.kind == "fit":
            n = scalebb.load_fit_to_db(db_path, args.file, meta_json_path=meta_path)
        else:
            n = scalebb.load_projection_to_db(
                db_path, args.file, meta_json_path=meta_path
            )
    except Exception as exc:
        print(f"[scalebb-load] error: {exc}")
        return 1
    print(f"[scalebb-load] loaded {n} rows")
    return 0


COMMANDS = {
    "init": cmd_init,
    "summary": cmd_summary,
    "build-incidence": cmd_build_incidence,
    "load-incidence": cmd_load_incidence,
    "export-incidence": cmd_export_incidence,
    "scalebb-fit": cmd_scalebb_fit,
    "scalebb-project": cmd_scalebb_project,
    "scalebb-heatmap": cmd_scalebb_heatmap,
    "scalebb-runs": cmd_scalebb_runs,
    "scalebb-load": cmd_scalebb_load,
    "scalebb-gen-table": cmd_scalebb_gen_table,
    "scalebb-apc-fit": cmd_scalebb_apc_fit,
    "scalebb-apc-project": cmd_scalebb_apc_project,
}


def main(argv: list[str] | None = None) -> int:
    parser = _make_parser()
    args = parser.parse_args(argv)
    config = db.load_config(args.config)
    handler = COMMANDS[args.command]
    return handler(args, config)


if __name__ == "__main__":
    sys.exit(main())
