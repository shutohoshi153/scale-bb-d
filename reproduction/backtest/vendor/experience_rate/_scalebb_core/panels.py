"""Panel CSV/parquet -> (ages, years, rate_matrix) loader.

Assembles (ages, years, rate_matrix) inputs for the Scale BB / APC models
from the tidy panels (mortality_apc_panel / age_period_panel) under
`KDB/data/processed/`.

Incorporates ``_load_panel`` / ``load_mortality_matrix`` /
``load_age_period_matrix`` from the research-side Scale BB disease script
into this package.

PANEL_DIR resolves to ``experience_rate.db.PROJECT_ROOT / "data" / "processed"``
and depends on the KDB directory layout.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from ..db import PROJECT_ROOT

PANEL_DIR: Path = PROJECT_ROOT / "data" / "processed"


def _load_panel(name: str) -> pd.DataFrame:
    pq = PANEL_DIR / f"{name}.parquet"
    cs = PANEL_DIR / f"{name}.csv"
    if pq.exists():
        return pd.read_parquet(pq)
    if cs.exists():
        return pd.read_csv(cs)
    raise FileNotFoundError(f"panel not found: {pq} or {cs}")


def _age_code_to_age_low(code: str) -> int | None:
    """Extract the representative age (lower bound of the interval) from ``age_code``.

    E.g. ``a00_04`` -> 0, ``a85_89`` -> 85, ``a00`` -> 0, ``a90p`` -> 90.
    Recap rows (``r65p``) and ``total`` return ``None`` and are excluded.
    """
    if not isinstance(code, str):
        return None
    if code == "total":
        return None
    if code.startswith("r"):  # exclude recap rows (r65p / r65_74 etc.)
        return None
    rest = code[1:]
    if rest.endswith("p"):
        return int(rest[:-1])
    if "_" in rest:
        return int(rest.split("_")[0])
    try:
        return int(rest)
    except ValueError:
        return None


def load_mortality_matrix(
    disease_ids: Iterable[str],
    *,
    sex: str = "total",
    age_min: int = 20,
    age_max: int = 89,
    year_min: int | None = None,
    year_max: int | None = None,
) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Return (ages, years, rate_matrix) per disease from ``mortality_apc_panel``."""
    df = _load_panel("mortality_apc_panel")
    df = df[df["age_is_total"] == False].copy()  # noqa: E712
    df = df[df["age_is_recap"] == False].copy()  # noqa: E712
    df["age_low"] = df["age_code"].map(_age_code_to_age_low)
    df = df.dropna(subset=["age_low"])
    df["age_low"] = df["age_low"].astype(int)
    df = df[(df["age_low"] >= age_min) & (df["age_low"] <= age_max)]
    df = df[df["sex"] == sex]
    if year_min is not None:
        df = df[df["year"] >= year_min]
    if year_max is not None:
        df = df[df["year"] <= year_max]

    out: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for did in disease_ids:
        sub = df[df["disease_id"] == did]
        if sub.empty:
            print(f"[warn] no rows for disease_id={did}; skipped")
            continue
        piv = sub.pivot_table(
            index="age_low", columns="year", values="rate_per_100k", aggfunc="mean"
        ).sort_index()
        ages = piv.index.to_numpy(dtype=int)
        years = piv.columns.to_numpy(dtype=int)
        rates = piv.to_numpy(dtype=float)
        out[did] = (ages, years, rates)
    return out


def load_age_period_matrix(
    *,
    sex: str = "total",
    section: str = "total",
    age_min: int = 5,
    age_max: int = 85,
    year_min: int | None = None,
    year_max: int | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return ``age_period_panel`` (all-disease combined utilization rate) as a matrix."""
    df = _load_panel("age_period_panel")
    df = df[df["age_is_recap"] == False].copy()  # noqa: E712
    df = df[df["age_is_total"] == False].copy()  # noqa: E712
    df["age_low"] = df["age_code"].map(_age_code_to_age_low)
    df = df.dropna(subset=["age_low"])
    df["age_low"] = df["age_low"].astype(int)
    df = df[(df["age_low"] >= age_min) & (df["age_low"] <= age_max)]
    df = df[(df["sex"] == sex) & (df["section"] == section)]
    if year_min is not None:
        df = df[df["year"] >= year_min]
    if year_max is not None:
        df = df[df["year"] <= year_max]
    piv = df.pivot_table(
        index="age_low", columns="year", values="rate_per_100k", aggfunc="mean"
    ).sort_index()
    return (
        piv.index.to_numpy(dtype=int),
        piv.columns.to_numpy(dtype=int),
        piv.to_numpy(dtype=float),
    )


__all__ = [
    "PANEL_DIR",
    "load_mortality_matrix",
    "load_age_period_matrix",
]
