**日本語** | [English](SCRIPTS.en.md)

# SCRIPTS — backtest 各スクリプトの処理解説

本書は `reproduction/backtest/` に同梱される実行スクリプト（シェル 1 本 + Python 8 本）の**処理内容**を、入力・処理・出力の観点から個別に解説する。パッケージ全体の位置づけ・クイックスタート・期待数値は [README.md](README.md) を、Python ファイルごとの詳細な設計書（関数仕様・出力列定義まで）は [docs/](docs/README.md) を参照。

## 全体の処理フロー

```
data/raw/5-15_*.csv ─┐
data/disease_estat_mapping.csv ─┴─► [1] build_panel.py
                                        │  data/disease_panel_mortality.csv
                                        ▼
              [2] run_backtest.py ──── [3] run_baselines.py     (×3 cutoff: 2014/2021/2022)
                    │ validation_summary.csv     │ validation_summary_baseline.csv ほか
                    ▼                            ▼
              [4] compare_cutoffs.py       [5] compute_directional_accuracy.py
                    │ output/cutoff_comparison/   │ output/directional/
                    ▼                            ▼
              [6] make_calibration_recovery_figure.py   (図 6.3)
                    ▼
              [7] make_paper_figures.py   (→ ../../sections/figures/)
```

各スクリプトは冒頭で `import _paths` するだけで、同梱データと `vendor/` のアルゴリズムコアが解決される（他ディレクトリへの依存なし）。

---

## run_all.sh — ワンショット再現ドライバ

上記フロー全体を正しい順序・正しい引数で一括実行するシェルスクリプト。

- `set -euo pipefail` で途中失敗時に即停止し、`cd "$(dirname "$0")"` で自ディレクトリに移動してから実行する（`import _paths` の解決のため）。
- Python 実行体は「環境変数 `PY`」→「リポジトリルートの `.venv/bin/python`」→「`python3`」の優先順で選ぶ。
- 実行内容: ① `build_panel.py` → ② `run_backtest.py` と `run_baselines.py` を 3 つの cutoff（2014 → `output/`、2021 → `output/cutoff_2021/`、2022 → `output/cutoff_2022/`）で実行 → ③ `compare_cutoffs.py` → ④ `compute_directional_accuracy.py` → ⑤ `make_calibration_recovery_figure.py` → ⑥ `make_paper_figures.py`。

## _paths.py — 自己完結パス層

パッケージ内で使う**全パス定義を集約する唯一のモジュール**。ロジックは持たない。

- `RAW_VITAL_CSV`（5-15 表の生 CSV）、`DISEASE_MAPPING`、`PANEL`（`build_panel.py` の出力 = 後段の入力）、`OUTPUT_DIR` を定義する。
- import された時点で `vendor/` を `sys.path` に挿入する副作用を持ち、これにより各スクリプトの `from experience_rate._scalebb_core.model import ...` が同梱コアに解決される。
- 元スクリプトはリポジトリルート相対で `EAS/src` 等を参照していたが、その差し替え箇所を本モジュール 1 か所に閉じ込めている（各スクリプト側の改変点には `# [REPRO]` マーカー）。

## build_panel.py — [1] 5-15 表 → 疾病パネル（§3.1）

人口動態統計 5-15 表（死因×性×5歳階級×年次、1950–2024）の生 CSV から、後段すべてが読む tidy 形式のパネル `data/disease_panel_mortality.csv` を構築する。

処理内容:

1. 生 CSV を読み、列名の BOM を除去。`表章項目` で「死亡数」と「死亡率」の行に分割する。
2. `性別`（総数/男/女）→ `sex` スラグ（total/male/female）、`年齢(5歳階級)` ラベル → `age_low`（0, 5, …, 100。「総数」「不詳」は除外）、`時間軸(年次)` → 整数 `year` に変換する。
3. `死因年次推移分類_code`（Hi コード）を、スクリプト冒頭の `DISEASE_TO_HICODE` 辞書で 8 疾病スラグ（cancer, diabetes, hypertensive, heart_disease, cerebrovascular, liver, kidney, total）に写像する。2017 年の分類改定により cancer と hypertensive は 2017 年版コード（`Hi022017` / `Hi042017`）側に全期間が格納されている点に注意。虚血性心疾患（heart_ischemic）は 5-15 表の分類に存在しないため対象外。
4. 死亡率と死亡数を `(disease_id, sex, year, age_low)` で結合し、`rate_per_100k`・`deaths` 列を持つロング形式で出力する（8 疾病 × 3 性別 × 75 年 × 21 年齢階級）。
5. 検算用に疾病×性別ごとの行数・年数・年齢数の要約 `data/panel_summary.csv` も出力する。

出力が同梱の照合用 `data/prebuilt_disease_panel_mortality.csv` と一致することが再現の第一チェックポイントとなる。

## run_backtest.py — [2] ScaleBB fit/project + 検証（§3.2）

パネルを読み、疾病×性別ごとに vendored Scale BB コア（式 3.1–3.6）で学習・射影し、検証期間の実績と突き合わせる。

CLI 引数: `--train-cutoff`（既定 2014）、`--validation-end`（既定 2024）、`--output-subdir`（`output/` 直下か `output/cutoff_*/` かの切替）、`--base-level`（投影起点の水準: `observed` 既定 / `mean_obs` / `smoothed`。[ADD 2026-09-03] 論文 §3.2.2 式 3.6 と §5.4）、`--base-obs-points`（`mean_obs` の観測点数、既定 3）。

処理内容:

1. **行列化** — `build_matrix()` が対象疾病・性別・年齢 20–89 歳・cutoff 年以前のデータを「年齢×年」の率行列にピボットする。
2. **fit/project** — `ScaleBBConfig`（ハイパーパラメータは EAS 既定と同一: 長期改善率 L=+1%、収束年 P=2035、λ_row=40、λ_col=20（暦年グリッド化に伴い 2026-09-02 に 40→20）、2階差分、90歳以降テーパー）で `fit_scale_bb()` → `project_scale_bb()` を呼ぶ。
3. **fit テーブル** — 観測値（`observed_train`）・平滑化値（`smoothed`）・射影値（`projected`）を kind 列で区別したロング形式 `tables/fit_long.csv` に落とす。
4. **検証テーブル** — 検証年の実績と射影を突き合わせ、`error`（予測−実績）、`rel_error`、`abs_rel_error` を計算して `tables/validation_long.csv` に出力する。実績が 0 のセルは相対誤差を NaN とする。
5. **集計** — `summarize()` が疾病×性別ごとの MAPE（実績>0 のセルの `abs_rel_error` 平均×100）、RMSE、bias（`error` 平均）、平均相対 bias を `tables/validation_summary.csv` に、`summarize_per_year()` が年次内訳を `tables/validation_by_year.csv` に出力する。
6. **作図** — sex=total について、代表年齢（40/60/75 歳）の観測・平滑化・射影・実績の軌跡図 `figures/<disease>_<sex>_trajectory.png`（対数軸）と、疾病別 MAPE・bias 年次推移 `figures/overall_mape_bias_by_year.png` を出力する。

## run_baselines.py — [3] 非 ScaleBB ベースライン（§3.3.1）

同一のバックテスト設定で 3 つのベースライン手法を走らせ、ScaleBB と比較可能な形の成果物を出力する。

3 手法（いずれも年齢別に独立に予測）:

- `naive_last` — cutoff 年の観測率をそのまま全検証年に据え置く。
- `mean_3pts` — 直近 3 観測点の平均を据え置く。
- `loglin_trend` — cutoff までの直近 `--trend-window` 年（既定 15 年）で log(率) を年次に OLS 回帰し、指数外挿する（正の観測が 3 点未満の年齢は予測不能として NaN）。

CLI 引数は `run_backtest.py` と同じ 3 つに `--trend-window` を加えた 4 つ。

処理内容: 手法×疾病×性別×年齢×年のロング表を作り、`run_backtest.py` と同一の定義で MAPE/RMSE/bias を集計（`validation_long_baseline.csv` / `validation_summary_baseline.csv`）。さらに **先行して生成済みの** `validation_summary.csv`・`validation_by_year.csv`（ScaleBB 側）を読み込んで結合し、手法比較表（`method_comparison_summary.csv`、MAPE ワイド表 + ScaleBB との差分列を持つ `method_comparison_MAPE_wide.csv`、年次内訳 `method_comparison_by_year.csv`）と比較図 2 枚（`baseline_vs_scalebb_mape.png`、`method_comparison_by_year.png`）を出力する。このため**同一 cutoff の `run_backtest.py` の後に実行する必要がある**。

## compute_directional_accuracy.py — [4] 方向性的中率 DA（§3.3.2、式 3.9–3.10）

3 つの cutoff の既存成果物（`fit_long.csv`、`validation_long.csv`、`validation_long_baseline.csv`）を読み、全手法の**方向性的中率**を計算する。CLI 引数なし。cutoff とサブディレクトリの対応はスクリプト内の `CUTOFFS` 定数に固定されている。

処理内容:

1. 各 cutoff について、`fit_long.csv` から cutoff 年の観測率（変化量の基準値 `rate_at_cutoff`）を取り、ScaleBB とベースライン 3 手法の予測・実績を結合する。
2. セル（疾病×性別×年齢×年）ごとに `actual_change = 実績 − rate_at_cutoff`、`predicted_change = 予測 − rate_at_cutoff` を計算し、符号が一致すれば的中とする。**実績変化が 0 のセルは真値が曖昧なため評価対象外**。予測変化が 0 のセル（`naive_last` は構造上すべて該当）は**外れ扱い** — 方向情報を持たない手法の DA が 0% になるのは仕様どおりの挙動である。
3. セル単位表 `directional_long.csv`、cutoff×手法×疾病×性別の集計 `directional_summary.csv`（DA%、評価セル数、無変化予測の比率 `flat_pred_pct` を含む）、sex=total 抜粋 `directional_summary_total.csv` を `output/directional/tables/` に出力する。
4. 図 3 枚 — ScaleBB の cutoff 別 DA 棒グラフ、4 手法×疾病×3 cutoff の比較、ScaleBB vs `loglin_trend`（方向シグナルを持つ最強ベースライン）の一騎打ち — を `output/directional/figures/` に出力する。いずれも多数派方向比率のマーカー付き（[CHG 2026-09-02] 50% 線は参考）。[ADD 2026-09-03] 参照規則 `majority_direction`（検証窓で多数派だった方向を全セルで答える事後基準）と、表 6.3 の勝敗表 `directional_winloss.csv` を出力する。

## compare_cutoffs.py — [5] 3 cutoff 横断比較（§4）

3 つの cutoff の `validation_summary.csv` と `method_comparison_MAPE_wide.csv` を読み、横断比較の表と図を `output/cutoff_comparison/` に出力する。CLI 引数なし。

処理内容:

1. ScaleBB の MAPE/RMSE/bias を cutoff 別サフィックス付き列で横結合し、cutoff 間の MAPE 差分列（2021−2014、2022−2014、2022−2021）を付けた `scalebb_cutoff_comparison.csv` を出力する。
2. 全手法の MAPE を cutoff 横断で結合した `method_cutoff_comparison.csv` を出力する。
3. 図 3 枚 — ScaleBB の cutoff 別 MAPE 棒グラフ、4 手法×3 cutoff のファセット図、「ScaleBB − 最良ベースライン」の MAPE ギャップ図（正 = ScaleBB 劣位。付随表 `scalebb_minus_best_baseline_gap.csv` も出力）。

## make_calibration_recovery_figure.py — [6] 再キャリブレーション実験（§6.5、図 6.3）

cutoff=2014 で方向をほぼ外す方向反転疾病 **liver / hypertensive**（sex=total）について、DA の回復を 5 設定で比較する実験スクリプト。CLI 引数なし。

- 5 設定: ①2014・既定（L=+1%, P=2035）、②2014・L=0%、③2014・L=0% かつ P=2020、④2021・既定、⑤2022・既定。②③が「キャリブレーション経路」（疾病別に L・P を再設定）、④⑤が「データ経路」（直近の反転トレンドを学習に取り込む）に対応する。
- **`output/` の既存成果物には依存しない**: 5 設定すべてについて本スクリプト内で fit/project から DA 計算（定義は `compute_directional_accuracy.py` と同一）までを再実行する。パネルは `data/disease_panel_mortality.csv`（無ければ同梱の prebuilt にフォールバック）から読む。
- 出力: `output/directional/tables/calibration_recovery.csv`、`output/directional/figures/calibration_recovery.png`、および論文掲載用コピー `../../sections/figures/fig_6_3_calibration_recovery.png`（コミット対象）。

## make_paper_figures.py — [7] 論文掲載図の生成・収集

論文本文が参照する図を `../../sections/figures/`（コミット対象）に揃える最終ステップ。CLI 引数なし。2 つの仕事をする:

1. **新規生成**（パネルから直接作図。パネル未構築時は prebuilt にフォールバック）
   - 図 3.1 `fig_3_1_input_panel_overview.png` — 代表年齢 2 つ（40 歳・75 歳）における 8 疾病の死亡率 1950–2024 推移（対数軸）。
   - 図 3.2 `fig_3_2_smoothing_before_after.png` — heart_disease を例に、2 次元 Whittaker–Henderson 平滑化（式 3.1–3.2）の前後を暦年断面・年齢断面で比較。
   - 図 3.3 `fig_3_3_blend_schematic.png` — 観測改善率が長期率 L に収束年 P へ向けてブレンドされる様子（式 3.5）の実例。
   - 図 4.1 `fig_4_1_backtest_design.png` — 3 cutoff の学習/検証窓と COVID-19 期間を示す模式図。
2. **収集** — `output/` 配下のバックテスト成果図 7 枚（軌跡図、MAPE/bias 推移、ギャップ図、DA 図など）を `COLLECT` 辞書に従い `fig_5_1`〜`fig_6_2` の名前でコピーする。`output/` は git 管理外のため、本文が参照する図だけをここでコミット対象に移す。未生成の図は警告してスキップする。

## vendor/experience_rate/_scalebb_core/ — 同梱アルゴリズムコア

EAS（`ValidationTools/EAS/src/experience_rate/_scalebb_core/`）からの**無改変コピー**。本パッケージのスクリプトが直接呼ぶのは `model.py` の `ScaleBBConfig` / `fit_scale_bb` / `project_scale_bb`（§3.2、式 3.1–3.6）のみ。`apc_model.py`（APC 拡張、付録 B）ほかは参照用に同梱されている。コアの実装解説は EAS 側ドキュメント（`設計書.md` / `design_document.en.md`）を参照。
