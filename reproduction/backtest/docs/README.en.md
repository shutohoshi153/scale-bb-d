[日本語](README.md) | **English**

# docs — Per-Script Design Documents for backtest

*English translation of [README.md](README.md) (as of 2026-08-06). If the versions disagree, the Japanese version is authoritative.*

Design documents (role, inputs/outputs, processing flow, function specifications, implementation notes) for each Python file in `reproduction/backtest/`. For the cross-script processing overview see [../SCRIPTS.en.md](../SCRIPTS.en.md); for the package description and expected reference numbers see [../README.en.md](../README.en.md).

| Target file | Design document | Paper sections |
|---|---|---|
| `_paths.py` | [_paths.en.md](_paths.en.md) | — (self-contained path layer) |
| `build_panel.py` | [build_panel.en.md](build_panel.en.md) | §3.1 |
| `run_backtest.py` | [run_backtest.en.md](run_backtest.en.md) | §3.2 (eqs. 3.1–3.6) |
| `run_baselines.py` | [run_baselines.en.md](run_baselines.en.md) | §3.4.1 |
| `compute_directional_accuracy.py` | [compute_directional_accuracy.en.md](compute_directional_accuracy.en.md) | §3.4.2 (eqs. 3.11–3.12) → §6 |
| `compare_cutoffs.py` | [compare_cutoffs.en.md](compare_cutoffs.en.md) | §4 |
| `make_calibration_recovery_figure.py` | [make_calibration_recovery_figure.en.md](make_calibration_recovery_figure.en.md) | §6.5 (fig. 6.3) |
| `make_paper_figures.py` | [make_paper_figures.en.md](make_paper_figures.en.md) | §3/§4 explanatory figures, §5/§6 result figures |

Each design document has a Japanese original (`<name>.md`). For the implementation of `vendor/experience_rate/_scalebb_core/`, see the EAS-side documents (`設計書.md` / `design_document.en.md`).
