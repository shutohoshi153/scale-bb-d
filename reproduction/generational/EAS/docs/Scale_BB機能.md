**日本語** | [English](Scale_BB_features.en.md)

# Scale BB 拡張モデル機能ガイド (EAS 統合版)

本ドキュメントは、EAS に統合した **Scale BB 拡張モデル**
(2D Whittaker-Henderson 平滑化 + 長期率ブレンドによる将来投影)
の使い方・データフロー・運用手順をまとめたものです。

元実装（リサーチ側コア）は以下:

- `scripts/scale_bb_model.py`  … コアアルゴリズム
- `scripts/scale_bb_disease.py` … fit / project CLI (疾病発生率・死亡率対応)
- `scripts/visualize_scale_bb_heatmaps.py` … ヒートマップ/トラジェクトリ生成

EAS ラッパは `EAS/src/experience_rate/scalebb.py` にあり、
サブプロセス実行 → 結果 CSV/Parquet を読み込み → SQLite へロード、
までを一括処理します。

---

## 1. アーキテクチャ概要

```
┌─────────────── EAS (SQLite + CLI) ─────────────┐
│  CLI: python -m experience_rate scalebb-*     │
│  DB: scalebb_run / scalebb_improvement /      │
│      scalebb_projection                        │
└────────────────────┬───────────────────────────┘
                     │ subprocess + parquet/CSV I/O
                     ▼
┌────────── Research scripts (repo root) ────────┐
│  scripts/scale_bb_model.py  (core algorithm)   │
│  scripts/scale_bb_disease.py (fit / project)   │
│  scripts/visualize_scale_bb_heatmaps.py        │
└────────────────────┬───────────────────────────┘
                     │
                     ▼
  data/processed/ の age×period パネル (CSV)
  ├─ mortality_apc_panel.csv      (死亡率)
  └─ age_period_panel.csv         (受療率・患者調査)
```

**設計方針**

- コア算法は `scripts/` 配下に集約しリサーチ側でも再利用可能にする。
- EAS はあくまで「実行・永続化・参照」のラッパとして機能する。
- 実行結果は常に SQLite (`scalebb_run`/`scalebb_improvement`/`scalebb_projection`)
  に保存し、過去実行との比較 / 回帰分析 / 監査証跡 を確保する。

---

## 2. DB スキーマ

### 2.1 scalebb_run

実行ごとに 1 行を追加する履歴テーブル。`config_json` に
`ScaleBBConfig` を完全シリアライズ保存する。

| カラム | 型 | 説明 |
|---|---|---|
| run_id | TEXT PK | `sb_fit_` / `sb_proj_` + UUID |
| kind | TEXT | `fit` / `projection` |
| source_panel | TEXT | `mortality_apc` / `age_period` |
| diseases | TEXT | 対象 disease_id のカンマ区切り |
| sex | TEXT | `total` / `male` / `female` |
| section | TEXT | `total` / `inpatient` / `outpatient` |
| age_min, age_max | INTEGER | 分析対象年齢レンジ |
| year_min, year_max | INTEGER | 観測年レンジ |
| long_term_rate | REAL | 長期率 L (projection のみ) |
| convergence_year | INTEGER | 収束年 P (projection のみ) |
| horizon_year | INTEGER | 投影終了年 |
| lam_row, lam_col | REAL | Whittaker-Henderson 平滑化係数 |
| config_json | TEXT | ScaleBBConfig の JSON |
| source_file | TEXT | ロード元 Parquet/CSV |
| created_at | TEXT | `datetime('now')` |

### 2.2 scalebb_improvement (Phase 1 結果)

```
PRIMARY KEY (run_id, disease_id, sex, section, age, year)
```

- `rate_observed` : 入力率 (per 100,000)
- `rate_smoothed` : Whittaker-Henderson 2D 平滑化後率
- `improvement_observed` : 観測率ベースの年率改善率
- `improvement_smoothed` : 平滑化率ベースの年率改善率

### 2.3 scalebb_projection (Phase 2 結果)

```
PRIMARY KEY (run_id, disease_id, sex, section, age, year)
```

- `is_observed` : 1 = 観測年, 0 = 将来投影年
- `improvement_final` : 原論文 h(y) 式で長期率 L に線形収束させた改善率
- `rate_projected` : base_year から `improvement_final` で累積生成した投影率

インデックス:
- `idx_scalebb_improvement_disease_year`
- `idx_scalebb_projection_disease_year`
- `idx_scalebb_projection_observed`

---

## 3. CLI リファレンス

すべて `python -m experience_rate <subcommand>` で実行。
`--config` オプションで `EAS/config.yaml` のパスを切り替え可能。

### 3.1 scalebb-fit (Phase 1)

観測率の 2D 平滑化 + 改善率抽出 → DB ロード。

```powershell
python -m experience_rate scalebb-fit `
    --source mortality `
    --disease cancer heart_disease cerebrovascular `
    --sex total `
    --age-min 20 --age-max 89 `
    --year-min 1990 `
    --lam-row 40 --lam-col 40
```

出力: `data/processed/scalebb_fit.parquet` (上書き) / `scalebb_improvement` テーブル。

### 3.2 scalebb-project (Phase 2)

長期率 L へ線形収束させ、horizon 年まで将来投影。

```powershell
python -m experience_rate scalebb-project `
    --long-term-rate 0.01 `
    --convergence-year 2035 `
    --horizon 2050
```

デフォルトでは `data/processed/scalebb_fit.parquet` を入力として使用。
`--fit-file <path>` で任意の fit 結果を指定可能。

### 3.3 scalebb-heatmap (可視化)

疾病別のヒートマップ (observed / smoothed / BB blended) と
年齢別 rate トラジェクトリ (log scale) を PNG 出力。

```powershell
python -m experience_rate scalebb-heatmap `
    --source mortality `
    --disease cancer heart_disease cerebrovascular `
    --sex total --age-min 20 --age-max 89 --year-min 1990 `
    --long-term-rate 0.01 --convergence-year 2035 --horizon 2050
```

デフォルト出力先: `EAS/output/scalebb_figures/*.png`。

### 3.4 scalebb-runs

履歴を一覧表示。

```powershell
python -m experience_rate scalebb-runs --last 20
```

### 3.5 scalebb-load

既存の fit/projection CSV/Parquet を DB に後入れロード
(別マシンで計算した結果を EAS に取り込む場合など)。

```powershell
python -m experience_rate scalebb-load --kind fit --file data/processed/scalebb_fit.parquet
python -m experience_rate scalebb-load --kind projection --file data/processed/scalebb_projection.parquet
```

## 4. 典型的なワークフロー

### 4.1 初期セットアップ

```powershell
cd c:\Github\IAJ_IT\EAS
pip install -r requirements.txt        # numpy, scipy, matplotlib, seaborn を含む
python -m experience_rate --config config.yaml init
```

### 4.2 全疾病 × 性別 total の総合投影

```powershell
# 1) Fit
python -m experience_rate scalebb-fit `
    --source mortality --disease cancer heart_disease cerebrovascular `
    --sex total --age-min 20 --age-max 89 --year-min 1990

# 2) Project
python -m experience_rate scalebb-project `
    --long-term-rate 0.01 --convergence-year 2035 --horizon 2050

# 3) Heatmap
python -m experience_rate scalebb-heatmap `
    --source mortality --disease cancer heart_disease cerebrovascular `
    --sex total --age-min 20 --age-max 89 --year-min 1990 `
    --long-term-rate 0.01 --convergence-year 2035 --horizon 2050

# 4) 確認
python -m experience_rate summary
python -m experience_rate scalebb-runs --last 10
```

### 4.3 SQL での結果取得例

```sql
-- 最新 projection run を取得
SELECT run_id FROM scalebb_run
WHERE kind = 'projection'
ORDER BY created_at DESC LIMIT 1;

-- がん 60歳の 2020年 vs 2040年 投影率比較
SELECT age, year, rate_projected, improvement_final, is_observed
FROM scalebb_projection
WHERE run_id = :run_id
  AND disease_id = 'cancer'
  AND age = 60
  AND year IN (2020, 2040)
ORDER BY year;
```

---

## 5. 主要パラメータの決め方

| パラメータ | デフォルト | 指針 |
|---|---|---|
| `lam_row` / `lam_col` | 40 / 40 | 年齢方向/年次方向の平滑化強度。原著 Report 相当。ノイズの強い小カテゴリでは 80-100 へ増やす |
| `long_term_rate` L | 0.01 (1%) | 長期の年率改善率。SOA Scale BB は 1% を既定。疾病特性に応じ 0.005-0.02 で感度分析推奨 |
| `convergence_year` P | 2035 | 観測改善率が L へ完全収束する年。Scale BB 原著では 2027 を使用 |
| `horizon` | 2050 | 投影終了年。主力保険の責任準備金評価期間に合わせる |
| `age_min` / `age_max` | **20 / 89** | 若年層商品にも対応。20 歳以上は 5 歳階級で連続しており mortality panel で欠損なし。小児 (0-14) は別モデル推奨 |

---

## 6. トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| `FileNotFoundError: scale_bb_disease.py` | EAS が repo root を見つけられない | `REPO_ROOT` が `EAS/src/experience_rate/scalebb.py` 冒頭で正しく解決されているか確認 |
| `IndexError: index N is out of bounds` | pivot 時に NaN 列が drop され行列寸法が食い違う | `scale_bb_disease.py` の `_pivot()` ヘルパで全 age×year を reindex 済み。独自改修時は再現注意 |
| `scalebb_run` に何も表示されない | `load_to_db=False` で実行した / DB ファイルが別 | `config.yaml` の `paths.database` を確認 |
| 図が出力されない | `EAS/output/scalebb_figures` に PNG が無い | `scalebb-heatmap` を先に実行 |

---

## 7. ファイル一覧

| 種別 | パス |
|---|---|
| DB スキーマ | `EAS/sql/01_schema.sql` (末尾 3 テーブル) |
| EAS ラッパ | `EAS/src/experience_rate/scalebb.py` |
| CLI | `EAS/src/experience_rate/cli.py` (`scalebb-*` サブコマンド) |
| コア算法 | `scripts/scale_bb_model.py` |
| fit/project CLI | `scripts/scale_bb_disease.py` |
| 可視化 | `scripts/visualize_scale_bb_heatmaps.py` |
| 出力 (fit/proj) | `data/processed/scalebb_{fit,projection}.parquet` |
| 出力 (図) | `EAS/output/scalebb_figures/*.png` |
| 理論背景 | `PDF/researchmortalityimprovebbreport.pdf`, `data/summary/abstract_draft_v2_ja.md` |

