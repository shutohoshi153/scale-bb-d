**日本語** | [English](_paths.en.md)

# 設計書 — `_paths.py`（自己完結パス層）

> スクリプト横断の概要は [../SCRIPTS.md](../SCRIPTS.md)、パッケージ全体は [../README.md](../README.md) を参照。

## 1. 役割と位置づけ

本パッケージ（`reproduction/backtest/`）を、リポジトリの他ディレクトリに依存せず単体実行可能にするための**唯一のパス定義モジュール**。処理ロジックは持たず、パス定数の定義と `sys.path` への `vendor/` 追加のみを行う。

元スクリプト群は `ROOT = Path(__file__).resolve().parents[2]` でリポジトリルートを辿り `EAS/src`・`ScaleBB_Research/data/raw`・`MedicalInsuranceProduct/` を参照していたが、2026-07 のリポジトリ再編でこれらは無効化された。その差し替えを本モジュール 1 か所に閉じ込めることで、各スクリプト側の改変を「先頭のパスアンカー数行（`# [REPRO]` マーカー付き）」に限定している。

## 2. 公開定数

| 定数 | 値（`HERE` = 本ファイルのあるディレクトリ） | 用途 |
|---|---|---|
| `HERE` | `Path(__file__).resolve().parent` | 全パスのアンカー |
| `DATA_DIR` | `HERE / "data"` | 同梱入力データの置き場 |
| `RAW_VITAL_CSV` | `DATA_DIR / "raw" / "5-15_死因_性_5歳階級_年次_死亡数率__0003411659.csv"` | 人口動態統計 5-15 表の生 CSV（`build_panel.py` の入力） |
| `DISEASE_MAPPING` | `DATA_DIR / "disease_estat_mapping.csv"` | 疾病 → 死因コード対応表（§3.1.2 のドキュメント用） |
| `PANEL` | `DATA_DIR / "disease_panel_mortality.csv"` | `build_panel.py` の出力 = 後段全スクリプトの入力 |
| `OUTPUT_DIR` | `HERE / "output"` | 全成果物のルート（git 管理外） |
| `VENDOR_DIR` | `HERE / "vendor"` | 同梱アルゴリズムコアのルート |

## 3. import 時の副作用

モジュール読み込み時に `VENDOR_DIR` を `sys.path` の先頭に挿入する（重複挿入は回避）。これにより、各スクリプトの

```python
from experience_rate._scalebb_core.model import ScaleBBConfig, fit_scale_bb, project_scale_bb
```

が同梱の `vendor/experience_rate/` に解決される。**利用側は `import _paths` を他の import より前に書くだけでよい**。

## 4. 実装上の注意

- パスを追加・変更する場合は必ず本モジュールに集約し、各スクリプトへの直書きは避けること。
- `sys.path.insert(0, ...)` は先頭挿入のため、環境に同名パッケージ `experience_rate` が入っていても同梱コアが優先される。
