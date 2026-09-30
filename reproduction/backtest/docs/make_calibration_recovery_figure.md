**日本語** | [English](make_calibration_recovery_figure.en.md)

# 設計書 — `make_calibration_recovery_figure.py`（[6] 再キャリブレーション実験、§6.5 図 6.3）

> スクリプト横断の概要は [../SCRIPTS.md](../SCRIPTS.md)、パッケージ全体は [../README.md](../README.md) を参照。

## 1. 役割と位置づけ

cutoff = 2014 で方向をほぼ外す**方向反転疾病**（liver / hypertensive、sex = total）について、方向性的中率 DA がどの介入で回復するかを 5 設定の比較実験として実行し、論文図 6.3 を生成する。`run_all.sh` ステップ [5]。§6.5「方向性が反転する疾病の扱い」に対応する。

## 2. 実験設計（5 設定）

Scale BB の共通ハイパーパラメータ（`COMMON_CFG`: λ_row=λ_col=40、2階差分、90歳テーパー — `run_backtest.py` と同一）を固定し、**cutoff・長期改善率 L・収束年 P の 3 つだけ**を振る:

| ラベル | cutoff | L | P | 経路 |
|---|---|---|---|---|
| `2014_default` | 2014 | +1% | 2035 | §6.1 の再掲（基準） |
| `2014_L0` | 2014 | 0% | 2035 | キャリブレーション経路（L 差し替えのみ） |
| `2014_L0_P2020` | 2014 | 0% | 2020 | キャリブレーション経路（収束年の前倒し併用） |
| `2021_default` | 2021 | +1% | 2035 | データ経路（直近反転を学習に反映） |
| `2022_default` | 2022 | +1% | 2035 | データ経路（さらに 1 年） |

- **キャリブレーション経路**: 疾病別に L・P を再設定して方向を回復させる。
- **データ経路**: 直近トレンドを学習データに取り込んで回復させる。

## 3. 入出力

**入力**: `data/disease_panel_mortality.csv`（無ければ同梱の `prebuilt_disease_panel_mortality.csv` にフォールバック）。

**`output/` の既存成果物には依存しない** — 5 設定すべてについて fit/project から DA 計算までを本スクリプト内で再実行する。既定設定（`2014_default` 等）の DA は `compute_directional_accuracy.py` の出力（`directional_summary_total.csv`）と一致する（整合性チェックに使える）。

**出力**

| ファイル | 内容 |
|---|---|
| `output/directional/tables/calibration_recovery.csv` | 10 行（2 疾病 × 5 設定）。列: `disease`, `setting`, `cutoff`, `long_term_rate`, `convergence_year`, `n_cells_evaluable`, `dir_acc_pct` |
| `output/directional/figures/calibration_recovery.png` | 5 設定の DA 棒グラフ |
| `../../sections/figures/fig_6_3_calibration_recovery.png` | 上記の論文掲載用コピー（**コミット対象**） |

## 4. CLI 引数

なし。設定は冒頭の `SETTINGS` / `DISEASES` / `COMMON_CFG` 定数に固定。

## 5. 処理フロー（`main()`）

1. 出力ディレクトリ（`output/directional/` と `../../sections/figures/`）を作成し、パネルを読み込む。
2. 疾病 × 5 設定の 10 通りについて `directional_accuracy()` を呼び、評価セル数と DA% を収集して CSV 出力。
3. 棒グラフを描画: x 軸に 2 疾病、設定ごとに 5 本の棒。**色 = cutoff**（`scalebb_directional_per_cutoff.png` と同一配色: 2014 赤 / 2021 橙 / 2022 緑）、**ハッチ + 透過 = cutoff 2014 の再キャリブレーション設定**（`//` = L0、`xx` = L0+P2020）。各棒の上に DA 値を注記し、50% 基準線を引く。
4. 図を `output/` 側に保存し、`shutil.copyfile` で `sections/figures/fig_6_3_calibration_recovery.png` へコピーする。

## 6. 関数仕様

### `directional_accuracy(panel, disease, cutoff, L, P) -> (n_eval, da_pct)`
指定設定で fit/project し、DA を返す本体。

1. `build_matrix()` で cutoff 年以前・年齢 20–89 の学習行列を作る。
2. `ScaleBBConfig(last_observed_year=cutoff, horizon_year=2024, long_term_rate=L, convergence_year=P, **COMMON_CFG)` で `fit_scale_bb()` → `project_scale_bb(base_year=cutoff)`。
3. 検証年（cutoff+1 〜 2024）の実績と cutoff 年観測率をパネルから直接取り、セルごとに `sign(actual − rate_at_cutoff)` と `sign(predicted − rate_at_cutoff)` を比較する。**定義は `compute_directional_accuracy.py` と同一**（実績変化 0 のセルは評価対象外、欠損セルはスキップ）。
4. `(評価セル数, DA%[小数 2 桁])` を返す。

## 7. 実装上の注意

- 検証期間は設定間で異なる（cutoff 2014 → 10 年 / 2021 → 3 年 / 2022 → 2 年）ため、`n_cells_evaluable` も異なる。DA の比較は「同一疾病・同一定義での回復度合い」の比較であり、セル数を揃えた検定ではない。
- 図 6.3 は `make_paper_figures.py` の `COLLECT`（収集）対象ではなく、**本スクリプトが直接 `sections/figures/` に書く**唯一の図である。
- L・P 以外のハイパーパラメータを `run_backtest.py` と同一に保つことが実験の統制条件。変更時は両方を揃えること。
