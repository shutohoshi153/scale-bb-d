**日本語** | [English](compute_directional_accuracy.en.md)

# 設計書 — `compute_directional_accuracy.py`（[4] 方向性的中率 DA、§3.4.2 式 3.11–3.12）

> スクリプト横断の概要は [../SCRIPTS.md](../SCRIPTS.md)、パッケージ全体は [../README.md](../README.md) を参照。

## 1. 役割と位置づけ

3 つの cutoff の既存成果物を読み、ScaleBB とベースライン 3 手法について**方向性的中率（DA: 各セルで変化の符号を正しく当てた割合）**を計算する。`run_all.sh` ステップ [4]。結果は論文 §6 の議論の土台となる。

**前提**: 3 cutoff すべてについて `run_backtest.py` と `run_baselines.py` が実行済みであること。

## 2. DA の定義（式 3.11–3.12）

セル（疾病×性別×年齢×検証年）ごとに、**cutoff 年の観測率**を基準として:

```
actual_change    = actual_rate    − rate_at_cutoff
predicted_change = predicted_rate − rate_at_cutoff
的中 (match)      = sign(actual_change) == sign(predicted_change)
```

- **評価対象外**: `sign(actual_change) == 0` のセル（真の方向が曖昧なため。`evaluable` フラグで管理）。
- **外れ扱い**: `sign(predicted_change) == 0` のセル。`naive_last` は構造上全セルがこれに該当し DA = 0% となる — 「無変化予測は方向情報を持たない」ことを明示するのが設計意図。
- DA% = 的中セル数 ÷ 評価対象セル数 × 100。

## 3. 入出力

**入力**（cutoff → 読込元は `CUTOFFS` 定数に固定: 2014→`output/`、2021→`output/cutoff_2021/`、2022→`output/cutoff_2022/`）

| ファイル | 用途 |
|---|---|
| `tables/fit_long.csv` | `kind == "observed_train"` かつ `year == cutoff` の行から基準値 `rate_at_cutoff` を取得 |
| `tables/validation_long.csv` | ScaleBB の予実（method=`scalebb` を付与） |
| `tables/validation_long_baseline.csv` | ベースライン 3 手法の予実 |

**出力**（`output/directional/` 配下）

| ファイル | 内容 |
|---|---|
| `tables/directional_long.csv` | セル単位。`actual_change`, `predicted_change`, `actual_sign`, `pred_sign`, `match`, `evaluable`, `cutoff` 列を含む |
| `tables/directional_summary.csv` | cutoff×手法×疾病×性別。`n_cells_evaluable`, `n_matches`, `dir_acc_pct`, `n_flat_preds`, `flat_pred_pct` |
| `tables/directional_summary_total.csv` | 上記の sex=total 抜粋 |
| `figures/scalebb_directional_per_cutoff.png` | ScaleBB の疾病×cutoff 別 DA 棒グラフ |
| `figures/method_directional_comparison.png` | 4 手法×疾病の DA、cutoff ごとに 3 パネル |
| `figures/scalebb_vs_loglin_directional.png` | ScaleBB vs `loglin_trend` の一騎打ち（3 パネル） |

図はいずれも 50%（コイントス）の基準破線付き、縦軸 0–100%。

## 4. CLI 引数

なし。cutoff とサブディレクトリの対応・図タイトルはスクリプト冒頭の `CUTOFFS` 定数（`(cutoff, subdir, title)` のリスト）に固定されている。

## 5. 処理フロー（`main()`）

1. 各 cutoff について `compute_directional()` を呼び、セル単位表を連結して `directional_long.csv` に出力。
2. `summarize()` で cutoff×手法×疾病×性別に集計し、`directional_summary.csv` と sex=total 抜粋を出力。
3. 図 3 枚を描画（下記）。
4. sex=total の DA を疾病 ×（cutoff, 手法）のピボットで標準出力に表示。

## 6. 関数仕様

### `load_observed_at_cutoff(subdir, cutoff) -> DataFrame`
`fit_long.csv` から cutoff 年の観測値を抽出し、`rate_at_cutoff` 列にリネームして返す（キー: disease, sex, age_low）。

### `load_val(subdir) -> DataFrame`
ScaleBB の `validation_long.csv`（method=`scalebb` を付与）とベースラインの `validation_long_baseline.csv` を共通列に揃えて縦結合する。

### `compute_directional(cutoff, subdir) -> DataFrame`
予実表に基準値を左結合し、変化量・符号・`match`・`evaluable` を計算する。`actual_change` / `predicted_change` / `rate_at_cutoff` のいずれかが欠損する行は除外。

### `summarize(long_df) -> DataFrame`
`evaluable == True` の行のみを cutoff×手法×疾病×性別でグループ化し、DA% と、無変化予測セルの数・比率（`n_flat_preds` / `flat_pred_pct`）を集計する。

## 7. 作図の設計意図

- **図 1**（ScaleBB × cutoff）: cutoff を後ろへずらすほど方向反転疾病の DA が回復する「データ経路」を示す。
- **図 2**（4 手法比較）: `naive_last` の DA=0% を含め、手法間の方向シグナルの有無を俯瞰する。図タイトルに 0% の理由を明記。
- **図 3**（vs `loglin_trend`）: 方向シグナルを明示的に持つ最強ベースラインとの公平な一騎打ち。

## 8. 実装上の注意

- 集計・作図の分母は常に `evaluable` セル。`directional_long.csv` には評価対象外セルも残る（`evaluable=False`）ため、二次分析時はフィルタすること。
- `rate_at_cutoff` は平滑化値ではなく**観測値**（`observed_train`）を使う。`make_calibration_recovery_figure.py` の DA 計算もこの定義に揃えてある。
