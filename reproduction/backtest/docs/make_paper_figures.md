**日本語** | [English](make_paper_figures.en.md)

# 設計書 — `make_paper_figures.py`（[7] 論文掲載図の生成・収集）

> スクリプト横断の概要は [../SCRIPTS.md](../SCRIPTS.md)、パッケージ全体は [../README.md](../README.md) を参照。

## 1. 役割と位置づけ

論文本文（`sections/`）が参照する図を `../../sections/figures/`（**コミット対象**）に揃える最終ステップ（`run_all.sh` ステップ [6]）。2 つの仕事をする:

1. **新規生成** — 本文 §3・§4 用の説明図 4 枚をパネルから直接作図する。
2. **収集** — `output/` 配下（git 管理外）のバックテスト成果図のうち、本文 §5・§6 が参照する 7 枚を論文用ファイル名でコピーする。

## 2. 入出力

**入力**: `data/disease_panel_mortality.csv`（無ければ同梱の `prebuilt_disease_panel_mortality.csv` にフォールバック — パネル未構築でも新規生成分は動く）、`vendor/` のコア、および収集対象の `output/` 配下の図。

**出力**（すべて `../../sections/figures/`）

| ファイル | 種別 | 内容 |
|---|---|---|
| `fig_3_1_input_panel_overview.png` | 生成 | 入力パネル概観（§3.1） |
| `fig_3_2_smoothing_before_after.png` | 生成 | 平滑化前後比較（§3.2.1、式 3.1–3.2） |
| `fig_3_3_blend_schematic.png` | 生成 | 改善率ブレンドの実例（§3.2.2、式 3.5） |
| `fig_4_1_backtest_design.png` | 生成 | 3 cutoff 設計の模式図（§4.2） |
| `fig_5_1_overall_mape_bias_by_year.png` | 収集 | ← `output/figures/overall_mape_bias_by_year.png` |
| `fig_5_2_heart_disease_total_trajectory.png` | 収集 | ← `output/figures/heart_disease_total_trajectory.png` |
| `fig_5_3_cancer_total_trajectory.png` | 収集 | ← `output/figures/cancer_total_trajectory.png` |
| `fig_5_4_scalebb_gap_vs_best_baseline.png` | 収集 | ← `output/cutoff_comparison/figures/…` |
| `fig_5_5_scalebb_cutoff_comparison.png` | 収集 | ← `output/cutoff_comparison/figures/…` |
| `fig_6_1_scalebb_directional_per_cutoff.png` | 収集 | ← `output/directional/figures/…` |
| `fig_6_2_scalebb_vs_loglin_directional.png` | 収集 | ← `output/directional/figures/…` |

図 6.3 のみ `make_calibration_recovery_figure.py` が直接生成する（本スクリプトの収集対象外）。

## 3. CLI 引数

なし（単体実行も可。収集対象が未生成の場合は警告してスキップする）。

## 4. 関数仕様（新規生成 4 図）

### `make_panel_overview(panel)` — 図 3.1
sex=total、代表年齢 40 歳・75 歳の 2 パネルに、8 疾病の死亡率 1950–2024 推移を対数軸で重ね描きする（率 0 の点は対数軸のため除外）。入力データの規模とトレンドの多様性を示す。

### `make_smoothing_before_after(panel, *, disease="heart_disease", sex="total", cutoff=2022)` — 図 3.2
cutoff 年までの行列に `fit_scale_bb()` のみ（射影なし）を適用し、2 次元 Whittaker–Henderson 平滑化（式 3.1–3.2）の前後を比較する。左パネル: 暦年方向の断面（年齢 40/60/75 歳）、右パネル: 年齢方向の断面（1970/2000/cutoff 年）。いずれも観測=マーカー、平滑化=実線、対数軸。

### `make_blend_schematic(panel, *, disease="heart_disease", sex="total", cutoff=2022, horizon=2045)` — 図 3.3
fit/project 後の最終改善率 `fit.improvement_final`（年率、%表示）を年齢 40/60/75 歳について 2000 年以降で描き、観測改善率が収束年 P に向けて長期率 L へブレンドされる様子（式 3.5）を示す。L の水平破線、cutoff 年と P の縦点線、その間の網掛けを付す。horizon=2045 まで射影して P 以降の平坦化も見せる。

### `make_backtest_design()` — 図 4.1
データを使わない模式図。3 つの cutoff 行それぞれに学習窓（青、1950–cutoff）と検証窓（赤、cutoff–2024、年数を注記）を水平バーで描き、COVID-19 期間（2020–2022）を灰色帯で重ねる。3 cutoff 設計が COVID 断絶をまたぐ位置関係を示す。

## 5. 収集処理

### `collect_backtest_figures()`
モジュール定数 `COLLECT`（`output/` 相対パス → 論文用ファイル名の辞書）に従い、存在する図を `shutil.copyfile` でコピーする。**存在しない図は `WARN` を表示してスキップ**し、処理は継続する（`run_all.sh` を通しで実行していれば全図が揃う）。

## 6. 実装上の注意

- ハイパーパラメータ `SCALE_BB_CONFIG` は `run_backtest.py` と同一（説明図と本検証の設定を一致させるため）。
- 図 3.2・3.3 の既定例示は heart_disease / cutoff 2022。例示疾病を変える場合はキーワード引数で指定できる。
- 出力先 `sections/figures/` はコミット対象。ファイル名は本文 LaTeX/Markdown から参照されるため、リネームは本文と同時に行うこと。
