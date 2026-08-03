"""SQLite database initialization and connection utilities."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = PROJECT_ROOT / "sql"


def load_config(config_path: str | Path = "config.yaml") -> dict:
    """Load config.yaml."""
    path = Path(config_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_scalebb_preset(
    config: dict,
    *,
    disease: str | None = None,
    sex: str | None = None,
) -> dict:
    """Return the merged settings from ``scalebb_presets`` for the (disease, sex) context.

    Merge precedence (later wins):
        defaults → diseases[disease] → sex[sex]

    Returned keys include ``lam_row``, ``lam_col``, ``lam_cohort``, ``long_term_rate``,
    ``convergence_year``, ``horizon_year``, ``age_min``, ``age_max``,
    ``covid_mode``, ``covid_years``, ``covid_weight``, etc.
    """
    presets = config.get("scalebb_presets", {}) or {}
    merged: dict = {}
    merged.update(presets.get("defaults", {}) or {})
    if disease:
        dmap = (presets.get("diseases", {}) or {}).get(disease, {}) or {}
        merged.update(dmap)
    if sex:
        smap = (presets.get("sex", {}) or {}).get(sex, {}) or {}
        merged.update(smap)
    return merged


def resolve_generational_preset(config: dict) -> dict:
    """Return ``scalebb_presets.generational`` (empty dict if undefined)."""
    presets = config.get("scalebb_presets", {}) or {}
    return dict(presets.get("generational", {}) or {})


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Establish a SQLite connection (foreign keys ON / row factory set)."""
    path = Path(db_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def _execute_script(conn: sqlite3.Connection, sql_file: Path) -> None:
    with sql_file.open("r", encoding="utf-8") as f:
        conn.executescript(f.read())


def initialize(db_path: str | Path, drop_existing: bool = False) -> None:
    """Build the schema and views.

    Args:
        db_path: Path to the SQLite file
        drop_existing: If True, delete any existing DB file before rebuilding
    """
    target = Path(db_path)
    if not target.is_absolute():
        target = PROJECT_ROOT / target
    if drop_existing and target.exists():
        target.unlink()

    conn = connect(target)
    try:
        _execute_script(conn, SQL_DIR / "01_schema.sql")
        medical_sql = SQL_DIR / "03_medical_schema.sql"
        if medical_sql.exists():
            _execute_script(conn, medical_sql)
        conn.commit()
    finally:
        conn.close()


def iter_tables(conn: sqlite3.Connection) -> Iterator[str]:
    """Enumerate all table names."""
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    for (name,) in cur.fetchall():
        yield name
