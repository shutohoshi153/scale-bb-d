**日本語** | [English](README.en.md)

# docs — backtest スクリプト別設計書

`reproduction/backtest/` の各 Python ファイルに対する設計書（役割・入出力・処理フロー・関数仕様・実装上の注意）。スクリプト横断の処理概要は [../SCRIPTS.md](../SCRIPTS.md)、パッケージ全体の説明・期待数値は [../README.md](../README.md) を参照。

| 対象ファイル | 設計書 | 論文対応 |
|---|---|---|
| `_paths.py` | [_paths.md](_paths.md) | —（自己完結パス層） |
| `build_panel.py` | [build_panel.md](build_panel.md) | §3.1 |
| `run_backtest.py` | [run_backtest.md](run_backtest.md) | §3.2（式 3.1–3.6） |
| `run_baselines.py` | [run_baselines.md](run_baselines.md) | §3.4.1 |
| `compute_directional_accuracy.py` | [compute_directional_accuracy.md](compute_directional_accuracy.md) | §3.4.2（式 3.11–3.12）→ §6 |
| `compare_cutoffs.py` | [compare_cutoffs.md](compare_cutoffs.md) | §4 |
| `make_calibration_recovery_figure.py` | [make_calibration_recovery_figure.md](make_calibration_recovery_figure.md) | §6.5（図 6.3） |
| `make_paper_figures.py` | [make_paper_figures.md](make_paper_figures.md) | §3・§4 説明図、§5・§6 成果図 |

各設計書には英訳（`<name>.en.md`）が併設されている。`vendor/experience_rate/_scalebb_core/` の実装解説は EAS 側ドキュメント（`設計書.md` / `design_document.en.md`）を参照。
