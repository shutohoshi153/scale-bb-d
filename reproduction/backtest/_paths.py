"""Self-contained path layer for the reproduction package.

Purpose:
    The single path-definition module that lets this package
    (reproduction/backtest/) run standalone, without depending on any
    other directory of the repository.
    The original research scripts resolved their input data and the
    algorithm core relative to the research repository root; this package
    bundles all input data and the algorithm core, and resolves them here.

Note for reviewers:
    - The only modification relative to the original scripts is the few
      path-anchor lines at the top. The algorithm, aggregation and plotting
      logic are untouched (the diff is traceable via ``git diff``).
    - As soon as ``import _paths`` runs, the bundled ``vendor/`` directory is
      added to ``sys.path``, so
      ``from experience_rate._scalebb_core.model import ...`` resolves as is.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Anchor all paths on this file's directory (reproduction/)
HERE = Path(__file__).resolve().parent

# --- Input data (bundled) ------------------------------------------------
DATA_DIR = HERE / "data"
RAW_VITAL_CSV = (
    DATA_DIR / "raw"
    / "estat_5-15_deaths_by_cause_sex_age_0003411659.csv"
)

# Output of build_panel.py = the PANEL read by the downstream scripts
PANEL = DATA_DIR / "disease_panel_mortality.csv"

# --- Output ----------------------------------------------------------------
OUTPUT_DIR = HERE / "output"

# --- Bundled algorithm core (experience_rate._scalebb_core) -----------------
VENDOR_DIR = HERE / "vendor"
if str(VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(VENDOR_DIR))
