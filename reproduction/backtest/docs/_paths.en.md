[日本語](_paths.md) | **English**

# Design Document — `_paths.py` (self-contained path layer)

*English translation of [_paths.md](_paths.md) (as of 2026-08-06). If the versions disagree, the Japanese version is authoritative.*

> For the cross-script overview see [../SCRIPTS.en.md](../SCRIPTS.en.md); for the package as a whole see [../README.en.md](../README.en.md).

## 1. Role and position

The **single path-definition module** that makes this package (`reproduction/backtest/`) runnable standalone, without depending on any other directory in the repository. It contains no processing logic — only path constants and the insertion of `vendor/` into `sys.path`.

The original scripts walked to the repository root via `ROOT = Path(__file__).resolve().parents[2]` and referenced `EAS/src`, `ScaleBB_Research/data/raw`, and `MedicalInsuranceProduct/`; the 2026-07 repository reorganization invalidated those paths. By confining the substitution to this one module, the modifications on each script's side are limited to "a few path-anchor lines at the top (marked `# [REPRO]`)".

## 2. Public constants

| Constant | Value (`HERE` = directory containing this file) | Purpose |
|---|---|---|
| `HERE` | `Path(__file__).resolve().parent` | Anchor for all paths |
| `DATA_DIR` | `HERE / "data"` | Location of the bundled input data |
| `RAW_VITAL_CSV` | `DATA_DIR / "raw" / "5-15_死因_性_5歳階級_年次_死亡数率__0003411659.csv"` | Raw CSV of Vital Statistics table 5-15 (input of `build_panel.py`) |
| `DISEASE_MAPPING` | `DATA_DIR / "disease_estat_mapping.csv"` | Disease → cause-of-death code mapping table (documentation for §3.1.2) |
| `PANEL` | `DATA_DIR / "disease_panel_mortality.csv"` | Output of `build_panel.py` = input of every downstream script |
| `OUTPUT_DIR` | `HERE / "output"` | Root of all generated artifacts (not under git) |
| `VENDOR_DIR` | `HERE / "vendor"` | Root of the bundled algorithm core |

## 3. Import-time side effect

On module load, `VENDOR_DIR` is inserted at the head of `sys.path` (duplicate insertion is avoided). This makes each script's

```python
from experience_rate._scalebb_core.model import ScaleBBConfig, fit_scale_bb, project_scale_bb
```

resolve to the bundled `vendor/experience_rate/`. **Callers only need to write `import _paths` before the other imports.**

## 4. Implementation notes

- When adding or changing paths, always centralize them in this module; avoid hard-coding paths in individual scripts.
- Because `sys.path.insert(0, ...)` prepends, the bundled core takes precedence even if a package named `experience_rate` is installed in the environment.
