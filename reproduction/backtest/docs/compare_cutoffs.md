**日本語** | [English](compare_cutoffs.en.md)

# 設計書 — `compare_cutoffs.py`（[5] 3 cutoff 横断比較、§4）

> スクリプト横断の概要は [../SCRIPTS.md](../SCRIPTS.md)、パッケージ全体は [../README.md](../README.md) を参照。

## 1. 役割と位置づけ

3 つの学習 cutoff（2014 / 2021 / 2022）の実行結果を横断的に比較し、「cutoff を後ろへずらす（= 直近データを学習に取り込み、予測ホライズンを縮める）と精度がどう変わるか」を表と図にまとめる。`run_all.sh` ステップ [3]。論文 §4（検証設計）および §5.3 に対応する。

**前提**: 3 cutoff すべてについて `run_backtest.py` と `run_baselines.py` が実行済みであること。

## 2. 入出力

**入力**（`CUTOFFS` 定数で固定: 2014→`output/`、2021→`output/cutoff_2021/`、2022→`output/cutoff_2022/`）

| ファイル | 用途 |
|---|---|
| `tables/validation_summary.csv` | ScaleBB の疾病×性別 MAPE / RMSE / bias / 相対 bias |
| `tables/method_comparison_MAPE_wide.csv` | 4 手法の MAPE ワイド表 |

**出力**（`output/cutoff_comparison/` 配下）

| ファイル | 内容 |
|---|---|
| `tables/scalebb_cutoff_comparison.csv` | ScaleBB の 4 指標 × 3 cutoff の横結合（列名サフィックス `_2014` / `_2021` / `_2022`）+ MAPE 差分列 `delta_MAPE_2021_vs_2014` / `delta_MAPE_2022_vs_2014` / `delta_MAPE_2022_vs_2021` |
| `tables/method_cutoff_comparison.csv` | 4 手法 × 3 cutoff の MAPE ロング表 + cutoff 間差分列 |
| `tables/scalebb_minus_best_baseline_gap.csv` | cutoff×疾病ごとの「ScaleBB MAPE − 最良ベースライン MAPE」（正 = ScaleBB 劣位） |
| `figures/scalebb_cutoff_comparison.png` | ScaleBB の疾病別 MAPE、3 cutoff 並列棒グラフ（sex=total） |
| `figures/method_cutoff_comparison.png` | 4 手法×疾病の MAPE、cutoff ごとの 3 パネル（sex=total） |
| `figures/scalebb_gap_vs_best_baseline.png` | ギャップ棒グラフ（0 線付き。論文図 5.4 の元） |

## 3. CLI 引数

なし。

## 4. 処理フロー（`main()`）

1. **ScaleBB 横断表** — `load_scalebb()` で各 cutoff の `validation_summary.csv` を読み、指標列に cutoff サフィックスを付けて `(disease, sex)` キーで順次マージする。cutoff 間の MAPE 差分列を追加し出力・標準出力表示。
2. **手法横断表** — `load_wide()` で各 cutoff の MAPE ワイド表を読み、`melt` で `(disease, sex, method, MAPE_<cutoff>)` のロング形式に変換して cutoff 横断でマージ。差分列を付けて出力。
3. **図 1** — sex=total の ScaleBB MAPE を疾病別に 3 cutoff 並列の棒グラフで描く（MAPE_2014 昇順に並べる）。
4. **図 2** — 手法×疾病×cutoff のファセット棒グラフ（3 パネル、y 軸共有）。
5. **図 3 + 付随表** — cutoff×疾病ごとに、ScaleBB MAPE から 3 ベースラインの最小 MAPE を引いたギャップ（pp）を計算し、表と棒グラフを出力する。

## 5. 関数仕様

### `load_scalebb(cutoff_subdir) -> DataFrame`
指定サブディレクトリ（`None` なら `output/` 直下）の `validation_summary.csv` から `disease`, `sex` + `KEEP` の 4 指標列（`MAPE_pct`, `RMSE_per100k`, `bias_per100k`, `mean_rel_bias_pct`）を返す。

### `load_wide(cutoff_subdir) -> DataFrame`
同様に `method_comparison_MAPE_wide.csv` を読む。

## 6. 実装上の注意

- マージは内部結合のため、いずれかの cutoff で欠けている疾病×性別は横断表から落ちる。
- ギャップ計算の「最良ベースライン」は cutoff×疾病ごとに独立に選ばれる（固定の手法ではない）。
- 期待される代表値（cancer/total/hypertensive の MAPE × 3 cutoff）は [../README.md](../README.md) の「期待される主要数値」を参照。
