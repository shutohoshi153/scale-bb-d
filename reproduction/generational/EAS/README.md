**日本語** | [English](README.en.md)

# 予定発生率テーブル生成環境 (SQLite + Python)

人口データ由来の発生率 (Incidence Rate) パネルと **Scale BB / APC 拡張モデル** による
予定発生率テーブル生成を担う、**SQLite + Python 製の再現実行環境**。

> **本再現環境の範囲について**
> 本研究では実績の保有 (In-Force)・異動 (Movement)・請求データを一切使用せず、
> 経験率 (A/E) 分析も利用しません。そのため元システムが備える
> 個人医療保険インポータ (`ins_*` テーブル群 / `import-*` コマンド)、
> 経験率分析 (`analyze` / `analyze-benchmark`)、Web UI (`serve`) は
> **本配布物から除外**しています。同梱しているのは人口統計 (e-Stat / 全国がん登録)
> のみを入力とする経路です。

## 特徴

- **SQLite で完結**: 外部依存なし（pandas / PyYAML / tabulate / pyarrow / xlrd / openpyxl）で動作
- **疾病発生率 (incidence rate) パネル**: 人口データ (e-Stat 患者調査・人口動態・
  全国がん登録) から算出した 4 種の発生率 (`registry` / `initial_visit` / `discharge` /
  `mortality`) を `population_incidence` テーブルに保持
- **Scale BB 拡張モデル**: SOA (2012) Mortality Improvement Scale BB を疾病発生率/死亡率
  に応用拡張。2D Whittaker-Henderson 平滑化による改善率抽出と、長期率 L への線形収束
  ブレンドによる将来投影を CLI から実行可能
  (`scalebb_run` / `scalebb_improvement` / `scalebb_projection` に永続化)
- **APC 拡張 + 世代投影**: コホート罰則付き APC 分解と、発行年別 1D 予定発生率テーブルの
  生成 (`predicted_rate_generational`)

## プロジェクト構成

```
EAS/
├── README.md                       # 本ファイル
├── requirements.txt
├── config.yaml                     # 観察年度終了月等の設定
├── sql/
│   └── 01_schema.sql               # テーブル DDL (parameters / rider_def / incidence / scalebb)
├── src/
│   └── experience_rate/
│       ├── __init__.py
│       ├── __main__.py
│       ├── db.py                   # 接続・初期化ユーティリティ
│       ├── etl.py                  # incidence パネル ロード (sp_etl 相当)
│       ├── cli.py                  # CLI エントリポイント
│       ├── scalebb.py              # Scale BB (AP) ラッパ
│       ├── scalebb_apc.py          # APC 拡張ラッパ
│       ├── scalebb_gen.py          # 世代投影テーブル生成
│       └── _scalebb_core/          # アルゴリズムコア (2D WH / コホート罰則 / 投影)
├── scripts/
│   ├── panel_helpers.py            # 疾病パネル構築の共通ヘルパ
│   ├── build_mortality_incidence_panel.py  # 人口動態ベースの発生率
│   ├── build_initial_visit_panel.py        # Z70 (初診受療率) ベース
│   ├── build_cancer_registry_panel.py      # 全国がん登録ベース (最高品質)
│   ├── build_los_panel.py                  # 平均在院日数パネル
│   ├── build_discharge_panel.py            # 退院フロー (Z10÷LOS×365)
│   ├── build_incidence_panel.py            # 上記を統合して incidence_panel 生成
│   └── analyze_standard_life_table.py      # 標準生命表との整合性検証
├── data/
│   ├── RowData/                    # 全国がん登録 (NCR) 原本
│   ├── lifetable/                  # 標準生命表 (整合性検証用)
│   └── processed/                  # incidence_panel / mortality_apc_panel / rider_disease_map 等
└── docs/
    ├── 設計書.md
    └── Scale_BB機能.md              # Scale BB 拡張モデルの CLI/DB 仕様
```

## セットアップ

```powershell
# 依存ライブラリをインストール (pandas + PyYAML + tabulate + fastapi + uvicorn ...)
pip install -r requirements.txt
```

## クイックスタート

```powershell
# 1. DB を初期化 (既存ファイル削除)
$env:PYTHONPATH = "src"
python -m experience_rate init --drop

# 2. 疾病発生率パネル (incidence_panel) を生成・DB にロード
python -m experience_rate build-incidence       # e-Stat/NCR → incidence_panel.csv
python -m experience_rate load-incidence        # incidence_panel → population_incidence

# 3. 行数サマリ確認
python -m experience_rate summary

# 4. APC fit → 投影 → 発行年別 予定発生率テーブル
python -m experience_rate scalebb-apc-fit --source mortality --sex male `
    --disease cancer heart_disease cerebrovascular --use-preset
python -m experience_rate scalebb-apc-project `
    --fit data/processed/scalebb_apc_fit_male.parquet --use-preset
python -m experience_rate scalebb-gen-table --use-preset `
    --output-dir data/processed/predicted_rate
```

> 予定発生率テーブルの完全な再現手順 (男女 × 3 疾病、基準出力との突合) は
> 一つ上の階層の [`../README.md`](../README.md) §4 を参照。

## 主要コマンド一覧

| コマンド | 説明 |
| --- | --- |
| `init --drop` | SQLite DB を初期化 (スキーマ構築 + parameters 投入) |
| `summary` | 各テーブルの行数を表示 |
| `build-incidence` | e-Stat + 全国がん登録から疾病発生率パネル (`incidence_panel.csv/parquet`) を生成 |
| `load-incidence --data-dir DIR` | 疾病発生率パネルと `rider_disease_map.csv` を DB にロード |
| `export-incidence --output FILE [--rate-type ...] [--disease ...] [--year N] [--sex 0/1/2]` | `population_incidence` から条件付き CSV 出力 |
| `scalebb-fit --source ... --disease ... --age-min N --age-max M` | Scale BB Phase 1 (2D 平滑化 + 改善率抽出) を実行し DB にロード |
| `scalebb-project --long-term-rate L --convergence-year P --horizon Y` | Scale BB Phase 2 (長期率ブレンド + 将来投影) を実行し DB にロード |
| `scalebb-heatmap --source ... --disease ...` | Scale BB スタイルのヒートマップ/投影図 (PNG) を `output/scalebb_figures/` へ出力 |
| `scalebb-apc-fit --source ... --sex ... --disease ... [--use-preset]` | APC 拡張 (コホート罰則 + γ コホート効果 + COVID ダミー) を実行し DB にロード |
| `scalebb-apc-project --fit PATH [--use-preset]` | APC fit 結果を長期率 L へブレンドして将来投影し DB にロード |
| `scalebb-gen-table --run-id ID [--use-preset] --output-dir DIR` | 世代投影により発行年別 1D 予定発生率テーブルを生成 |
| `scalebb-runs [--last N] [--kind fit/projection]` | `scalebb_run` 履歴を表示 |
| `scalebb-load --kind fit/projection --file PATH` | 既存の fit/projection CSV/Parquet を DB に後入れロード |

## 疾病発生率 (Incidence Rate) データソース

| `rate_type` | 出典 | 品質 | 対象期間 | 用途 |
| --- | --- | --- | --- | --- |
| `registry` | 全国がん登録 (NCR) | **A** (真罹患率) | 2016-2023 | がん特約のベンチマーク |
| `initial_visit` | 患者調査 Z70 (外来初診受療率) | B (近似) | 2023 断面 | 生活習慣病・初診フロー |
| `discharge` | 患者調査 Z10 + H20-47 平均在院日数 | C (近似) | 2023 断面 | 入院給付系特約 |
| `mortality` | 人口動態統計 5-15 (粗死亡率) | D (下限) | 1950-2020 | 主契約死亡・致死性疾患 |

各 rate_type の詳細・計算式は [`docs/設計書.md`](./docs/設計書.md) 参照。

## Scale BB 拡張モデル

SOA (2012) Mortality Improvement Scale BB を疾病発生率/死亡率に応用拡張した
モデルを、EAS に組み込んだ形で実行・永続化できる。
アルゴリズム本体は `scripts/scale_bb_model.py` (repo root) にあり、
EAS 側は薄いラッパ (`src/experience_rate/scalebb.py`) として動作する。

### ワークフロー (CLI)

```powershell
$env:PYTHONPATH = "src"

# 1) Fit: 観測率を 2D Whittaker-Henderson 平滑化 → 改善率抽出 → DB ロード
python -m experience_rate scalebb-fit `
    --source mortality `
    --disease cancer heart_disease cerebrovascular `
    --sex total --age-min 20 --age-max 89 --year-min 1990

# 2) Project: 長期率 L=1% へ 2035 年収束, 2050 年まで投影
python -m experience_rate scalebb-project `
    --long-term-rate 0.01 --convergence-year 2035 --horizon 2050

# 3) Heatmap: 疾病別 age×year 改善率ヒートマップ (PNG)
python -m experience_rate scalebb-heatmap `
    --source mortality `
    --disease cancer heart_disease cerebrovascular `
    --sex total --age-min 20 --age-max 89 --year-min 1990 `
    --long-term-rate 0.01 --convergence-year 2035 --horizon 2050

# 4) 履歴確認
python -m experience_rate scalebb-runs --last 10
```

### 格納テーブル

| テーブル | 内容 |
| --- | --- |
| `scalebb_run` | 実行メタ (kind, source, diseases, λ, L, P, horizon, config_json, created_at) |
| `scalebb_improvement` | Phase 1 結果: age × year × (rate_observed, rate_smoothed, improvement_observed, improvement_smoothed) |
| `scalebb_projection` | Phase 2 結果: age × year (観測 + 投影) × (improvement_final, rate_projected, is_observed) |

詳細仕様・DB スキーマ・トラブルシューティングは
[`docs/Scale_BB機能.md`](./docs/Scale_BB機能.md) 参照。

