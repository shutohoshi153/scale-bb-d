**日本語** | [English](README.en.md)

# generational — 予定発生率表 生成スクリプトと追跡検証環境

> 本パッケージは `Paper_ICA2026/reproduction/` の一部です（旧 `CoAuthor_Share_20260711/05_reproduction/`
> から 2026-07-22 に移行）。論文 **§3.3（APC拡張）** の再現と、その前向き実行系である世代投影
> （発行年別 予定率テーブル生成。本文の章としては扱わず、本 README で説明）に対応します。
> 姉妹パッケージ `../backtest/`（点予測精度・方向性的中率、§3.4/§5/§6）とアルゴリズムコアを共有し、
> 両者を合わせて §3 全体を再現します。分担の全体像は `../README.md` を参照。

ScaleBB (APC拡張) による**予定疾病発生率テーブル**の生成パイプライン一式を、
共同執筆者の手元で再実行・追跡検証できる形で同梱したものです。
2026-07-15 に本ディレクトリのコピー上で一連の再現実行を行い、
基準出力と一致することを確認済みです（§5 参照）。


> [注記 2026-09-03] アルゴリズムコア `EAS/src/experience_rate/_scalebb_core/model.py` の投影起点が「基準年の平滑化率」から「基準年の観測率」（`ScaleBBConfig.base_level="observed"`、論文 §3.2.2 式 3.6 の記述どおり）に変更された。本パッケージの `reference_output/`・`reference_output_20260902/` は旧起点（平滑化率）で生成したものであり、現行コードで再実行すると予定率テーブルの水準が変わる（改善率経路は不変）。2026-09-03 に再実行し、修正後の参照出力を `reference_output_20260903/` に格納した（§5 参照。APC 版テーブルは数値不変、AP 版テーブルは平均 +1.1%）。現行コードで再現した出力は `reference_output_20260903/` と比較すること。

## 1. データ出所に関する重要な注記（誤解防止）

- **予定発生率表の入力データは e-Stat 人口動態統計の疾病別死亡率**
  （`EAS/data/processed/mortality_apc_panel.parquet`、死亡率を発生率のプロキシとして使用）です。
- **がん研究センター（国立がん研究センター）由来のデータ = 全国がん登録（NCR）罹患率**
  （`EAS/data/RowData/cancer_incidenceNCR(2016-2023).xls`、出典: 国立がん研究センター
  がん情報サービス「がん統計」（全国がん登録））は、
  予定率表の入力では**なく**、真の罹患率としての **最高品質（A-tier）ベンチマーク** に使われます
  （`EAS/scripts/build_cancer_registry_panel.py` が発生率パネル化 → `population_incidence` に
  `rate_type='registry'` として格納）。同梱している `.xls` は提供元からダウンロードした原本
  そのままであり、パネル化後の数値は本研究による加工物です（提供元は加工結果に責任を負いません）。
- 死亡率ベース予定率とがん登録罹患率ベースの乖離定量化は、仕様書
  `docs/apc_predicted_rate_tables_by_sex_20260423.md` §B.9 に**今後の課題**として記載されています。
- **用語について（2026-07-15 改題に伴う補足）:** 本パイプラインが生成する「予定発生率テーブル」は、
  実体としては**死因別死亡率**（人口10万対）から計算した率テーブルです。論文の枠組み（改題後）では、
  この死因別死亡率を **(i) 医療保険の疾病発生率に対する代理**、**(ii) 特定疾病死亡保障に対する
  対象そのもの（直接のアサンプション）** という二層で用います。ファイル名・旧ラベルの「発生率
  （incidence）」表記は製品面の呼称であり、入力・計算は一貫して死因別死亡率である点にご留意ください
  （アルゴリズムは入力の意味に非依存のため、再現結果・数値は不変）。

## 2. 構成

| パス | 内容 |
| --- | --- |
| `EAS/` | 実行環境（自己完結の SQLite + Python アプリのコピー）。スクリプト・アルゴリズムコア・設定・入力データを含む |
| `EAS/scripts/build_cancer_registry_panel.py` | **がん登録（NCR）→ 発生率パネル** 変換スクリプト |
| `EAS/data/lifetable/seimeihyo960718.xlsx` | 標準生命表（出典: 公益社団法人日本アクチュアリー会「標準生命表1996 / 2007 / 2018」の 7 系統を単一ブックに束ねたもの）。入力データの妥当性検証用（§4.3） |
| `EAS/src/experience_rate/_scalebb_core/` | ScaleBB / APC アルゴリズムコア（2D Whittaker-Henderson、コホート罰則、世代投影） |
| `EAS/config.yaml` | パラメータプリセット（現在は **20歳始（age20）版** の設定状態） |
| `docs/apc_predicted_rate_tables_by_sex_20260423.md` | **仕様・工程書**: 目的、入力、パイプライン全体図、全再現コマンド、結果サマリ |
| `docs/age20_pipeline_migration_20260423.md` | 20歳始拡張の経緯と設定変更 |
| `reference_output/` | **追跡検証用の基準出力**（研究側で生成済みの現行成果物のスナップショット） |
| `reference_output/predicted_rate_apc/` | APC版 予定率表（issue_age=40、発行年2024–2028） |
| `reference_output/predicted_rate_apc_age20/` | APC版 予定率表（issue_age=20） |
| `reference_output/predicted_rate_tables/` | 従来AP版（比較用） |
| `reference_output/scalebb_apc_*.parquet ほか` | fit / projection の中間成果物 |

リポジトリ原本: `EAS` は `ICA/ValidationTools/EAS/`、仕様書は `ICA/ScaleBB/Research/docs/`。
容量削減のため e-Stat 生データ（`estat_api/`, `estat_processed/`, 約235MB）は同梱していません
（パネル類は構築済みのものを `EAS/data/processed/` に同梱）。

> **経験率（A/E）分析機能の除外について**
> 本研究では実績の保有（In-Force）・異動（Movement）・請求データを一切使用せず、
> 経験率（A/E）分析も利用しません。そのため `EAS` 原本が備える以下の機能は
> **本配布物から除外**しています。同梱しているのは人口統計（e-Stat / 全国がん登録）
> のみを入力とする経路です。
>
> - 個人医療保険インポータ（`ins_*` テーブル群、`import-validate` / `import-table` /
>   `import-all` / `import-history`、YAML マッピング定義）
> - 経験率・ベンチマーク分析（`analyze` / `analyze-benchmark`）
> - Web UI / REST API（`serve`、FastAPI 一式）
> - サンプル契約データ生成（`generate_medical_sample.py` / `generate_lapse_sample.py`）
>
> 原本の該当機能を参照したい場合は `ICA/ValidationTools/EAS/` を参照してください。

## 3. セットアップ

Python 3.11+ を想定。すべて `EAS/` ディレクトリ直下で実行します。

```bash
cd Paper_ICA2026/reproduction/generational/EAS
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=src

python -m experience_rate init --drop   # SQLite スキーマ初期化
```

> 仕様書内のコマンド例は PowerShell 表記（`` ` `` 改行、`$env:PYTHONPATH`）かつ
> 旧ディレクトリ構成（`../data/processed/...`）です。本環境では bash +
> EAS 内相対パス（`data/processed/...`）に読み替えてください（下記が読み替え済み手順）。

## 4. 再現手順

### 4.1 予定発生率表（APC版、男女 × 3疾病）

```bash
# ① APC fit（2D WH平滑化 + コホート罰則 + COVIDダミー）
python -m experience_rate scalebb-apc-fit --source mortality --sex male \
  --disease cancer heart_disease cerebrovascular --use-preset --run-id male_repro

# ② projection（改善率 × 長期率Lブレンド、〜2100年）
python -m experience_rate scalebb-apc-project \
  --fit data/processed/scalebb_apc_fit_male.parquet --use-preset --run-id male_repro_proj

# ③ 世代投影テーブル（発行年別 1D [age]、log-linear 単年齢補間）
python -m experience_rate scalebb-gen-table --run-id male_repro_proj --use-preset \
  --output-dir data/processed/predicted_rate_repro

# female も --sex female / fit ファイル名 female で同様に実行
```

**注意**: 同梱の `config.yaml` は **age20 プリセット**（`age_min=20, issue_age=20, lam_col=60`）の
状態です。この設定での出力は `reference_output/predicted_rate_apc_age20/` に対応します。
issue_age=40 版（`reference_output/predicted_rate_apc/`）を再現する場合は、仕様書 §4.1 の
40歳始パラメータ（`age_min=40, lam_col=40, issue_age=40`）に `config.yaml` を戻すか、
CLI 引数で明示指定してください。

**2026-09-02 更新（平滑化グリッド修正と `lam_col` の再検討）**: アルゴリズムコア
（`EAS/src/experience_rate/_scalebb_core/model.py` / `apc_model.py`）に `expand_to_annual_grid` を追加し、
平滑化を暦年連続グリッド（欠測年は重み 0）上で行うよう修正した（`ScaleBBConfig.annual_grid=True` 既定。
従来は 1950, 1955, …, 2010, 2013, … の観測列を等間隔扱いしていたため、5 年刻み→年次の切替点で
改善率が過大になっていた。論文 §3.2.1 参照）。この修正に伴い `lam_col=60` を再検討した。
男女 × 3 疾病の APC fit で `lam_col ∈ {10, 20, 30, 40, 60, 80}` を掃引し、age20 移行時の採用理由
（若年 20–35 歳の改善率の年齢間粗さと年次変動の抑制）を同じ指標で測ると、暦年グリッド上の 60 は
旧グリッド上の 60 とほぼ同じ粗さ（2 階差分平均 0.16% 対 0.16%）で年次変動はより小さい
（直近 10 年の標準偏差 2.6% 対 3.1%）ため、**60 を据え置いた**。なお 2024 年終端の改善率は
`lam_col` に単調に依存する（8 系列平均で λ=20: 0.36%、40: 0.71%、60: 0.93%）ので、
用途に応じて変える場合はこの感度に留意すること。

### 4.2 がん登録（がん研究センター NCR）パネルの構築

```bash
python scripts/build_cancer_registry_panel.py                    # 単体実行（行数・内訳を表示）
python scripts/build_cancer_registry_panel.py --output data/processed/registry_panel.csv
python -m experience_rate load-incidence                          # 同梱の incidence_panel を DB へロード
python -m experience_rate export-incidence --rate-type registry \
  --output output/registry_rates.csv                             # 罹患率を条件付きで CSV 出力
```

がん登録（NCR）由来の罹患率は `population_incidence` に `rate_type='registry'`,
`quality_flag='A'` として格納されます（§1 のとおり予定率表の入力ではなく、
真の罹患率としての最高品質ベンチマーク）。本再現環境には契約データがないため、
経験率との A/E 対比は行いません（§2 の注記を参照）。

> **パネル再構築スクリプトについての注意**: `scripts/build_incidence_panel.py` /
> `build_los_panel.py` / `build_discharge_panel.py` / `build_initial_visit_panel.py` は
> e-Stat 生データ（`data/RowData/estat_processed/`、§2 のとおり容量削減のため**未同梱**）を入力とします。
> 未同梱のまま実行すると該当サブビルダが 0 行を返すため、同梱済みパネルを縮退版で
> 上書きしないよう、`build_incidence_panel.py` と `build_los_panel.py` は書き込みを中止します
> （意図的に上書きする場合のみ `--force`）。同梱パネルはそのまま使えるので、
> 通常の再現手順でこれらを再実行する必要はありません。

### 4.3 標準生命表との整合性検証（入力データの妥当性チェック）

```bash
python scripts/analyze_standard_life_table.py
```

公益社団法人日本アクチュアリー会公表の標準生命表（`data/lifetable/seimeihyo960718.xlsx`、
生保標準生命表 1996 / 2007 / 2018 および第三分野標準生命表 2007 / 2018 の 7 系統。
加工前の原データは同会公表の「標準生命表1996」「標準生命表2007」「標準生命表2018」）と、
本パイプラインの入力である e-Stat 人口動態の死因別死亡率（`population_incidence`,
`rate_type='mortality'`）を突合し、`ratio = population_rate / standard_rate` を算出します。
死亡保険用は安全割増により `ratio < 1`、年金開始後用は `ratio > 1` となることが
保険数理上の期待で、`[5] 妥当性チェック` に期待符号との一致が `[OK]` で表示されます
（第三分野は罹患率概念のため `[REF]` = 参考値）。

**予定発生率表の生成経路とは独立**した入力データの妥当性検証であり、
本スクリプトを実行しなくても §4.1 の再現結果は変わりません。
出力は `output/standard_vs_population_{band10,detail}.csv`、
`standard_vs_population_judgement.csv`、`standard_life_table_tidy.csv`、
`disease_breakdown_std2018_male_40_59.csv` に保存されます。
なお `population_incidence` を参照するため、先に §4.2 の `load-incidence` を実行してください。

## 5. 追跡検証の方法（実施済み）

再現出力を `reference_output/` と突き合わせます。

```bash
diff data/processed/predicted_rate_repro/predicted_rate_cancer_male_issue2026_ia20.csv \
     ../reference_output/predicted_rate_apc_age20/predicted_rate_cancer_male_issue2026_ia20.csv
```

**2026-07-15 実施の検証結果**: 本コピー環境で `init → scalebb-apc-fit（cancer, male）→
scalebb-apc-project → scalebb-gen-table` を実行し、`predicted_rate_cancer_male_issue2026_ia20.csv`
を基準出力と比較。**全46行が有効数字15桁レベルで一致**（相対差 ~1e-15、浮動小数点演算順序に
起因する最終桁のみの差）を確認しました。この検証実行の生成物
（`EAS/experience_rate.db`、`EAS/data/processed/scalebb_apc_fit_male.*` /
`scalebb_apc_projection_male.*`、`EAS/data/processed/predicted_rate_verify/`）は
そのまま残置しています。ゼロから再実行する場合は `init --drop` で DB を作り直してください。

**2026-09-02 再実行（グリッド修正後）**: `init --drop` から男女 × 3 疾病の fit → project → gen-table を修正後のコアで再実行した。**共著者が参照する `reference_output/` は修正前（2026-08 時点）のまま変更せず**、修正後の出力は新設の `reference_output_20260902/` に格納した（`predicted_rate_apc_age20/` 30 ファイル、`predicted_rate_apc/` 30 ファイル + マスター 2 本、`predicted_rate_tables/` 男女 30 ファイル + total 15 ファイル + マスター 3 本、`scalebb_apc_{fit,projection}_{male,female}.*`）。再実行の中間生成物（female の fit/projection、age40 版の fit/projection、AP 版の `scalebb_fit.*` / `scalebb_projection.*`、`predicted_rate_*_repro*/`）は `EAS/data/processed/_rerun_20260902/` にまとめ、`EAS/data/processed/` 直下と `EAS/experience_rate.db` は 2026-07-15 の検証 run の状態に戻した。修正前との差: age20 APC 版は率で最大 ±2.8%（多くは ±1〜2%。cancer male +1.4%、cerebrovascular female −1.5% など）、age40 APC 版は −3.3〜+0.7%、AP 版（男女）は −5.0〜+1.9%。観測終端 2024 年は年次点が多く、グリッド修正の影響が小さいためである。age40 版は仕様書 §4.2–4.3 の手順を `--age-min 40 --lam-col 40`（apc-fit）と `--issue-age 40 --age-min 40`（gen-table）の CLI 上書きで、AP 版は仕様書 §4.4 の手順で男女に加え sex=total も実行した（`reference_output/predicted_rate_tables/` に残る sex=total の 12 ファイルは 2026-04-22 の非補間 run の残骸で、修正後ディレクトリでは補間済み・発行年 2024–2028 の 15 ファイルになっている）。現行コードで再現した出力は `reference_output_20260902/` と比較すること。

**2026-09-03 再実行（投影起点の修正後）**: コアの投影起点の変更（`ScaleBBConfig.base_level="observed"`）と `apc_model.py` の修正（`dummy` モードの局所トレンド窓 `covid_trend_window`=15、γ(c) の線形成分除去とコホート軸平滑化 `lam_gamma`=25、`apply_cohort` オプション）を反映して、2026-09-02 と同じ手順（`init --drop` → age20 APC 男女 → age40 APC 男女（`--age-min 40 --lam-col 40` / `--issue-age 40 --age-min 40`）→ AP 男女 + total（仕様書 §4.4、`--issue-age 40 --age-min 40`））を再実行し、出力を新設の `reference_output_20260903/` に格納した（レイアウトは `reference_output_20260902/` と同一: `predicted_rate_apc_age20/` 30、`predicted_rate_apc/` 30 + マスター 2、`predicted_rate_tables/` 45 + マスター 3、`scalebb_apc_{fit,projection}_{male,female}.*`）。中間生成物は `EAS/data/processed/_rerun_20260903/` にまとめ、`EAS/data/processed/` 直下と `EAS/experience_rate.db` は再実行前の状態に戻した（`reference_output/`・`reference_output_20260902/` は変更していない）。`reference_output_20260902/` との差: **APC 版（age20・age40）の予定率テーブルは全 60 ファイルで数値が一致**（相対差 0）。理由は 2 つで、(i) 経験率集計処理側の APC 投影ラッパ `src/experience_rate/scalebb_apc.py` はコアの `project_scale_bb_apc` ではなく独自コードで投影しており、起点を依然として基準年の平滑化率に置いているため起点変更の影響を受けない、(ii) `dummy` モードの修正は 2020–2022 年の平滑化率のみを変える（fit の `rate_smoothed` は最大 6.0% 変化）ため、2024 年起点の改善率経路は不変であり、γ(c) は最大 0.165 変化したが投影に用いられない。**AP 版（`predicted_rate_tables/`）は起点が観測率に変わったため変化**: 発行年 2026 のファイルで平均 −0.5〜+3.9%（cancer male +3.9%、cancer total +2.5%、heart_disease male −0.5%）、単年齢セルの最大 36.5%（cerebrovascular female、若年の観測率と平滑化率のずれが大きいセル）。なお APC ラッパの起点が論文 §3.2.2（観測率）と食い違う点は本再実行の範囲外の課題として残る。

**2026-09-30 再実行（コホート罰則の格子修正後）**: `apc_model.py` のコホート罰則が出生コホートを辿っていなかった（5 歳階級 × 暦年 1 年刻みの格子で (i+1, j+1)、実年齢では (x+5, y+1) を結んでいた）点を修正し、(i+1, j+5) 方向に改めた（`cohort_year_step`、論文付録 B 式 B.2）。パッケージ外の作業コピーで `init --drop` → age20 APC 男女 → age40 APC 男女（`--age-min 40 --lam-col 40` / `--issue-age 40 --age-min 40`）を再実行し、出力を新設の `reference_output_20260930/` に格納した（`predicted_rate_apc_age20/` 30 + マスター 2、`predicted_rate_apc/` 30 + マスター 2、age20 版の `scalebb_apc_{fit,projection}_{male,female}.*`）。AP 版（`predicted_rate_tables/`）は `model.py` が不変のため再実行しておらず、`reference_output_20260903/` のものが引き続き有効である。`EAS/data/processed/` 直下と `EAS/experience_rate.db` は変更していない。`reference_output_20260903/` との差は大きい: 発行年 2026 のファイルの平均で age20 版 −15.9〜−3.7%（cancer female −15.9%、heart_disease female −13.5%、heart_disease male −13.2%、cerebrovascular male −11.4%、cerebrovascular female −5.4%、cancer male −3.7%）、age40 版 −16.4〜+4.6%（cancer male −16.4%、cancer female −9.2%、cerebrovascular female +4.6%）。罰則方向の修正で平滑化面の末端改善率が変わるためである。現行コードで再現した APC 版の出力は `reference_output_20260930/` と比較すること。

そのほかの検証手段:

- `python -m experience_rate scalebb-runs --last 10` — 実行履歴とパラメータ（config_json）の監査
- fit / projection の中間値は `reference_output/scalebb_apc_*.parquet` と比較可能
- DB スキーマ・格納件数の期待値は仕様書 §6.1 / §B.4 に記載

## 6. スクリプトの仕様・目的の参照先

| 知りたいこと | 参照先 |
| --- | --- |
| パイプラインの目的・入力・全体図・パラメータ・結果 | `docs/apc_predicted_rate_tables_by_sex_20260423.md` |
| 20歳始拡張の動機と設定差分 | `docs/age20_pipeline_migration_20260423.md` |
| 数理的定式化（APC・識別性） | `../../../ScaleBB/Research/docs/methodology_apc_extension_20260422.md`（論文 §3.3 に対応） |
| CLI 全般・DB スキーマ | `EAS/README.md`、`EAS/docs/Scale_BB機能.md` |
| NCR パネル化の入出力仕様 | `EAS/scripts/build_cancer_registry_panel.py` 冒頭 docstring |
