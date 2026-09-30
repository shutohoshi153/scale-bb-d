**日本語** | [English](run_baselines.en.md)

# 設計書 — `run_baselines.py`（[3] 非 ScaleBB ベースライン、§3.4.1）

> スクリプト横断の概要は [../SCRIPTS.md](../SCRIPTS.md)、パッケージ全体は [../README.md](../README.md) を参照。

## 1. 役割と位置づけ

`run_backtest.py` と**同一のバックテスト設定**（同一パネル・同一年齢域・同一 cutoff・同一検証年）で 3 つのベースライン手法を走らせ、ScaleBB と直接比較できる表・図を出力する。`run_all.sh` ステップ [2] 内で、各 cutoff の `run_backtest.py` の**直後**に実行される。

**前提**: 同一出力ディレクトリに ScaleBB 側の `validation_summary.csv`・`validation_by_year.csv` が生成済みであること（手法比較表の作成時に読み込むため）。

## 2. ベースライン手法の定義

いずれも年齢階級ごとに独立に予測する。

| method | 定義 |
|---|---|
| `naive_last` | cutoff 年の観測率を全検証年に据え置く（predicted_t = observed_cutoff） |
| `mean_3pts` | 年順で直近 3 観測点の平均（`nanmean`）を全検証年に据え置く |
| `loglin_trend` | cutoff までの直近 `--trend-window` 年（既定 15 年）について log(率) を年次に単回帰（OLS）し、検証年へ指数外挿する |

`loglin_trend` は正の有限観測が 3 点未満の年齢では係数を推定せず、予測は NaN（= 集計から除外）となる。

## 3. 入出力

**入力**: `_paths.PANEL`、および同一出力ディレクトリの `tables/validation_summary.csv`・`tables/validation_by_year.csv`（ScaleBB 側）。

**出力**（`output[/<subdir>]/` 配下）

| ファイル | 内容 |
|---|---|
| `tables/validation_long_baseline.csv` | 手法×疾病×性別×年齢×年のセル単位予実対比（`error`, `rel_error`, `abs_rel_error` 付き） |
| `tables/validation_summary_baseline.csv` | 手法×疾病×性別の MAPE / RMSE / bias / 相対 bias |
| `tables/method_comparison_summary.csv` | 上記に ScaleBB（method=`scalebb`）を縦結合した 4 手法比較 |
| `tables/method_comparison_MAPE_wide.csv` | 疾病×性別 × 手法の MAPE ワイド表 + `delta_<method>_minus_scalebb` 列 |
| `tables/method_comparison_by_year.csv` | sex=total の手法×疾病×年 MAPE（ScaleBB 含む） |
| `figures/baseline_vs_scalebb_mape.png` | 疾病別 4 手法 MAPE 棒グラフ（sex=total、ScaleBB の MAPE 昇順） |
| `figures/method_comparison_by_year.png` | 疾病別 8 パネルの年次 MAPE 推移（4 手法重ね描き） |

## 4. CLI 引数

| 引数 | 既定値 | 意味 |
|---|---|---|
| `--train-cutoff` | 2014 | 学習最終年 |
| `--validation-end` | 2024 | 検証最終年 |
| `--output-subdir` | `""` | `output/` 配下のサブディレクトリ |
| `--trend-window` | 15 | `loglin_trend` の回帰に使う年数（cutoff 年を含む）。`TREND_WINDOW_START = cutoff − window + 1` |

## 5. 処理フロー（`main()`）

1. 引数を可変グローバルに反映し、出力ディレクトリを作成。パネルを読み込む。
2. 全疾病 × 性別 {total, male, female} について `run_baselines_for()` を呼び、3 手法分のセル行を蓄積する。
3. `summarize()` で誤差列を付与しつつ手法×疾病×性別で集計し、`validation_long_baseline.csv` / `validation_summary_baseline.csv` を出力。
4. ScaleBB の `validation_summary.csv` を読み込んで縦結合し、`method_comparison_summary.csv` と MAPE ワイド表（ScaleBB との差分列付き）を出力。
5. sex=total についてセルから手法×疾病×年の MAPE を再集計し、ScaleBB の `validation_by_year.csv` と結合して `method_comparison_by_year.csv` を出力。
6. 比較図 2 枚を出力し、sex=total の MAPE ワイド表を標準出力に表示する。

## 6. 関数仕様

### `predict_naive_last(years_train, rates_train) -> (n_age,)`
年配列の最大値の列（cutoff 年）をそのまま返す。

### `predict_mean_3pts(years_train, rates_train) -> (n_age,)`
`argsort` で年順に並べた末尾 3 列の `nanmean`。観測が飛び飛びでも「直近 3 つの観測点」を使う（例: 2010, 2013, 2014）。

### `predict_loglin(years_train, rates_train, *, window_start) -> (intercept, slope)`
`year >= window_start` の列に限定し、年齢ごとに log(率) の単回帰係数を閉形式 OLS で求める。有効観測（有限かつ正）が 3 点未満、または年の分散が 0 の年齢は NaN のまま。予測値は `exp(a + b·year)` でブロードキャスト計算する。

### `build_panel_for(df, *, disease, sex) -> (ages, years_train, rates_train, val_actual)`
学習期間・検証期間それぞれをピボットし、検証側は学習側の年齢インデックスと検証年に `reindex` して行列の形を揃える。

### `make_validation_rows(method, disease, sex, ages, val_actual, predicted_per_year)`
(n_age × n_validation_years) の予測行列と実績行列をセル単位のロング行に展開する。

### `summarize(val_df) -> (summary, val_df_enriched)`
`run_backtest.py` と**同一の定義**で誤差列（actual ≤ 0 は相対誤差 NaN）を付与し、手法×疾病×性別で MAPE / RMSE / bias / 相対 bias を集計する。

## 7. 実装上の注意

- 精度指標の定義を `run_backtest.py` と一致させることが本スクリプトの要件（比較の公平性）。定義を変える場合は両方を同時に変更すること。
- 実行順依存: 同一 cutoff の `run_backtest.py` より先に実行すると、ScaleBB 集計ファイルの読み込みで失敗する。
- `naive_last` / `mean_3pts` は全検証年で同一値（フラット予測）であり、方向性的中率の計算では構造的に方向シグナルを持たない（詳細は `compute_directional_accuracy.py` の設計書参照）。
