**日本語** | [English](run_backtest.en.md)

# 設計書 — `run_backtest.py`（[2] ScaleBB fit/project + 検証、§3.2）

> スクリプト横断の概要は [../SCRIPTS.md](../SCRIPTS.md)、パッケージ全体は [../README.md](../README.md) を参照。

## 1. 役割と位置づけ

疾病パネルを読み、疾病×性別ごとに同梱の Scale BB コア（式 3.1–3.6）で「cutoff 年までの学習 → 検証期間への射影」を行い、実績と突き合わせて精度指標を集計する。`run_all.sh` ステップ [2] として **3 つの cutoff（2014/2021/2022）で 3 回実行**され、それぞれ `output/`・`output/cutoff_2021/`・`output/cutoff_2022/` に成果物を書く。

## 2. 入出力

**入力**: `_paths.PANEL`（`build_panel.py` の出力）、`vendor/` の `experience_rate._scalebb_core.model`。

**出力**（`output[/<subdir>]/` 配下）

| ファイル | 内容 |
|---|---|
| `tables/fit_long.csv` | 観測・平滑化・射影値のロング表。列: `disease`, `sex`, `age_low`, `year`, `kind`（`observed_train` / `smoothed` / `projected`）, `rate_per_100k` |
| `tables/validation_long.csv` | セル単位の予実対比。列: `disease`, `sex`, `age_low`, `year`, `actual_rate_per_100k`, `predicted_rate_per_100k`, `error`, `rel_error`, `abs_rel_error` |
| `tables/validation_summary.csv` | 疾病×性別の集計。列: `n_cells`, `MAPE_pct`, `RMSE_per100k`, `bias_per100k`, `mean_rel_bias_pct`, `MAPE_<初年/中間年/最終年>`, `RMSE_<初年/最終年>` |
| `tables/validation_by_year.csv` | 疾病×性別×年の集計（同指標） |
| `figures/<disease>_<sex>_trajectory.png` | 代表年齢の軌跡図（sex=total のみ生成） |
| `figures/overall_mape_bias_by_year.png` | 疾病別 MAPE / 相対 bias の年次推移（sex=total） |

## 3. CLI 引数

| 引数 | 既定値 | 意味 |
|---|---|---|
| `--train-cutoff` | 2014 | 学習に使う最終年 |
| `--validation-end` | 2024 | 検証期間の最終年（検証年は cutoff+1 〜 この年） |
| `--output-subdir` | `""` | `output/` 配下のサブディレクトリ名。空なら `output/` 直下（cutoff=2014 の既定挙動） |

引数はモジュールレベルの可変グローバル（`TRAIN_CUTOFF`, `VALIDATION_YEARS`, `OUT_TABLES`, `OUT_FIGS`）に `main()` で反映される。

## 4. 処理フロー（`main()`）

1. 引数を解析し、出力ディレクトリを作成。パネルを読み込む。
2. パネル中の全疾病 × 性別 {total, male, female} をループし、`run_one()` を呼ぶ（データが無い組合せはスキップ）。sex=total のみ `make_trajectory_plot()` で軌跡図を出力。
3. 全組合せの fit 表・検証表を連結して `fit_long.csv` / `validation_long.csv` に出力。
4. `summarize()` → `validation_summary.csv`、`summarize_per_year()` → `validation_by_year.csv` を出力し、`make_overall_plots()` で年次推移図を描く。

## 5. 関数仕様

### `build_matrix(df, *, disease, sex, year_max) -> (ages, years, rates)`
対象疾病・性別・年齢 20–89 歳（`AGE_MIN`/`AGE_MAX`）・`year <= year_max` の行を「年齢×年」に `pivot_table`（mean）し、年齢配列・年配列・率行列（NumPy）を返す。

### `run_one(df, *, disease, sex) -> (fit_df, val_df)`
1 つの疾病×性別についての本体処理。

1. `build_matrix()` で学習行列を作る（空・全非有限なら空 DataFrame を返してスキップ）。
2. `ScaleBBConfig(last_observed_year=TRAIN_CUTOFF, horizon_year=max(VALIDATION_YEARS), **SCALE_BB_CONFIG)` を作り、`fit_scale_bb()` → `project_scale_bb(base_year=TRAIN_CUTOFF)` を実行。
3. **fit 表**: 学習期間の観測値（`observed_train`）・平滑化値（`smoothed`）、および cutoff より後の射影値（`projected`）を kind 列付きロング形式に展開。
4. **検証表**: 検証年の実績をピボットして射影値と突き合わせ、以下を計算する。
   - `error = predicted − actual`
   - `rel_error = error / actual`。ただし **actual ≤ 0 のセルは NaN**（ゼロ除算の相対誤差は未定義）
   - `abs_rel_error = |rel_error|`

### `summarize(val_df) -> DataFrame`
実績・予測がともに非欠損のセルを疾病×性別でグループ化し、次を集計する。

| 指標 | 定義 |
|---|---|
| `MAPE_pct` | actual > 0 のセルの `abs_rel_error` 平均 × 100（式 3.9） |
| `RMSE_per100k` | 全セルの二乗誤差平均の平方根 |
| `bias_per100k` | `error` の平均（正 = 過大予測） |
| `mean_rel_bias_pct` | actual > 0 のセルの `rel_error` 平均 × 100（式 3.10） |
| `MAPE_<年>` / `RMSE_<年>` | 検証初年・中間年・最終年（RMSE は初年・最終年）の年別値。列名は検証期間から動的に決まる |

### `summarize_per_year(val_df) -> DataFrame`
同じ指標を疾病×性別×**年**の粒度で集計する（トレンド分析・作図用）。

### `make_trajectory_plot(disease, sex, fit_df, val_df)`
代表年齢 40/60/75 歳の 3 パネルで、観測（青○）・平滑化（橙実線）・射影（緑破線）・検証実績（赤×）を対数軸で重ね描きする。cutoff 年に縦点線。

### `make_overall_plots(per_year)`
sex=total について、左パネルに疾病別 MAPE の年次推移、右パネルに平均相対 bias の年次推移（0 線付き）を描く。

## 6. 定数・設定

**`SCALE_BB_CONFIG`** — EAS の `config.yaml > scalebb_presets` の既定と同一のハイパーパラメータ（§3.2.3）:

| キー | 値 | 意味 |
|---|---|---|
| `long_term_rate` | 0.01 | 長期改善率 L = +1%/年 |
| `convergence_year` | 2035 | 収束年 P |
| `lam_row` / `lam_col` | 40.0 / 40.0 | Whittaker–Henderson 平滑化の罰則強度（年齢方向/年方向） |
| `diff_order` | 2 | 差分次数 |
| `age_taper_start` / `age_taper_end` | 90 / 120 | 高齢域の改善率テーパー区間 |

`AGE_MIN, AGE_MAX = 20, 89` — 死亡率が非自明でマッピングが完全な年齢域に限定する。

## 7. 実装上の注意

- MAPE と RMSE で分母集合が異なる（MAPE は actual > 0 のみ、RMSE は非欠損全セル）。
- 図の生成は sex=total のみ（male/female は表のみ）。
- matplotlib は `Agg` バックエンド固定（ヘッドレス実行対応）。
- 3 cutoff の成果物は後段の `compare_cutoffs.py`・`compute_directional_accuracy.py` が読むため、ファイル名・列名の変更は後段へ波及する。
