**日本語** | [English](age20_pipeline_migration_20260423.en.md)

# 分析パイプライン 20 歳開始への全面移行 (2026-04-23)

## 1. 背景・目的

若年層向け医療保険商品 (学資保険・若年終身医療・若年がん保険) への適用を
想定し、これまで **40 歳開始** を既定としていた経験率・予定疾病発生率
算出パイプラインを **全階層で 20 歳開始** に再構築した。

本ドキュメントは、`EAS/data/RowData/` から生成される parquet パネル、
EAS CLI / Web UI / REST API、および研究用バックテスト/可視化スクリプト
までの **全レイヤの変更点と検証結果** を記録する。

## 2. 事前調査: 生データ層は既に 20 歳対応

### 2.1 `mortality_apc_panel.parquet` の年齢階級

```
全 age_code (22 階級):
  a00_04, a05_09, a10_14, a15_19,
  a20_24, a25_29, a30_34, a35_39,
  a40_44, a45_49, a50_54, a55_59,
  a60_64, a65_69, a70_74, a75_79,
  a80_84, a85_89, a90_94, a95_99, a100p, total
```

**結論**: mortality_apc_panel は **1950-2024 年の全期間 × 20 階級 × 3 疾病 ×
3 性別** で欠損なし。**生データからパネル構築までのスクリプトには年齢
フィルタが無い** (= 既に 20 歳対応)。

### 2.2 該当スクリプト (変更不要)

| スクリプト | 入力 | 出力 | 年齢フィルタ |
|---|---|---|---|
| `scripts/build_disease_panel.py` | e-Stat 5-15, Z3-2, Z4-4, Z5-2, Z68 | `mortality_apc_panel.parquet` 他 | **なし** (全年齢保持) |
| `EAS/scripts/build_mortality_incidence_panel.py` | `mortality_apc_panel.parquet` | `incidence_panel` (mortality) | **なし** |
| `EAS/scripts/build_incidence_panel.py` | 各 rate_type パネル | `incidence_panel.csv` | **なし** |
| `EAS/src/experience_rate/etl.py` | `incidence_panel.csv` | `population_incidence` テーブル | **なし** |

→ **生データ → panel → DB までは変更不要**。問題は下流の分析スクリプト・
CLI・Web UI に **age_min=40 が default でハードコード** されていた点。

## 3. 実施変更 — 全ファイル一覧

### 3.1 EAS 本体 (プロダクション)

| ファイル | 変更箇所 | 変更内容 |
|---|---|---|
| `EAS/config.yaml` | `scalebb_presets.defaults.age_min` | 40 → **20** |
| `EAS/config.yaml` | `scalebb_presets.defaults.lam_col` | 40.0 → **60.0** (若年ノイズ抑制) |
| `EAS/config.yaml` | `scalebb_presets.generational.issue_age` | 40 → **20** |
| `EAS/config.yaml` | `scalebb_presets.generational.age_min` | 40 → **20** |
| `EAS/src/experience_rate/cli.py` | `scalebb-fit --age-min default` | 40 → **20** |
| `EAS/src/experience_rate/cli.py` | `scalebb-heatmap --age-min default` | 40 → **20** |
| `EAS/src/experience_rate/cli.py` | `_merge_preset_apc` fallback | 40 → **20** |
| `EAS/src/experience_rate/scalebb.py` | `run_fit()` / `run_heatmap()` 引数 default | 40 → **20** (×2) |
| `EAS/src/experience_rate/scalebb_apc.py` | `run_apc_fit()` 引数 default | 40 → **20** |
| `EAS/src/experience_rate/web/app.py` | `ScaleBBFitRequest.age_min` | 40 → **20** |
| `EAS/src/experience_rate/web/app.py` | `ScaleBBFitRequest.lam_col` | 40.0 → **60.0** |
| `EAS/src/experience_rate/web/app.py` | `ScaleBBHeatmapRequest.age_min` | 40 → **20** |
| `EAS/src/experience_rate/web/static/index.html` | `#sb-fit-age-min` value 属性 | 40 → **20** |
| `EAS/docs/Scale_BB機能.md` | age_min 既定値表 / サンプルコード | 40 → **20** (5 箇所) |
| `EAS/README.md` | サンプルコード | 40 → **20** (2 箇所) |

### 3.2 研究用スクリプト (`scripts/`)

| ファイル | 変更箇所 | 変更内容 |
|---|---|---|
| `scripts/scale_bb_disease.py` | `load_mortality_matrix()` default | 40 → **20** |
| `scripts/scale_bb_disease.py` | `fit` / `run-all` argparse default | 40 → **20** (×2) |
| `scripts/backtest_ap_vs_apc.py` | `load_matrix()` default / argparse | 40 → **20** (×2) |
| `scripts/backtest_scalebb_vs_traditional.py` | `load_matrix()` default / argparse | 40 → **20** (×2) |
| `scripts/visualize_scale_bb_heatmaps.py` | argparse default | 40 → **20** |
| `scripts/build_traditional_predicted_rates.py` | `AGE_MIN` 定数 | 40 → **20** |
| `scripts/build_traditional_predicted_rates.py` | `AGE_CODE_TO_LOW` | **a20_24 〜 a35_39 追加** |

### 3.3 変更不要だったファイル

- `scripts/scale_bb_model.py` — 純粋な数値ルーチン。age_min パラメータを持たない
- `scripts/scale_bb_apc_model.py` — 同上
- `scripts/build_generational_rate_table.py` — 既に `default=0` (呼出し側で制御)
- `scripts/build_disease_panel.py` — 生データパネル構築、年齢フィルタなし

## 4. 検証: `--use-preset` 無しで 20 歳開始が効くか

### 4.1 スモークテスト

```powershell
$env:PYTHONPATH="src"; $env:PYTHONIOENCODING="utf-8"
# age-min を明示指定しない (新しい default=20 が効くことを確認)
python -m experience_rate scalebb-fit `
    --source mortality --disease cancer --sex male --year-min 1990 `
    --output ../data/processed/_smoketest_fit_age20.parquet
```

**期待結果**: `n_age=14` (20-24 〜 85-89 の 14 階級)、subprocess に
`--age-min 20 --age-max 89` が渡される。

**実行結果** (2026-04-23):

```
[fit] disease=cancer sex=male n_age=14 n_year=17 year_range=1990-2024
[saved] scalebb_improvement 238 rows (run_id=20260423T092649)
[scalebb] $ python scripts/scale_bb_disease.py fit --sex male `
         --age-min 20 --age-max 89 --output ...
```

**判定**: **合格**。明示指定なしで 20 歳開始 (`n_age=14`) で動作。

### 4.2 Web UI の default 値

- `http://localhost:8000` の Scale BB タブで Age Min 入力欄を確認
- `index.html#sb-fit-age-min` の `value="20"` が反映される

## 5. 運用影響

### 5.1 過去 run_id との互換性

| 項目 | 影響 |
|---|---|
| 既存 `scalebb_run` / `scalebb_improvement` / `scalebb_projection` テーブル | **変更なし**。各行は `run_id` で紐付くため、age_min=40 時代のデータも保持 |
| 既存 parquet 出力 (`scalebb_fit.parquet` 等) | **変更なし**。新規出力は 14 階級 (20-85)、旧は 10 階級 (40-85) |
| 既存 `predicted_rate_generational` エントリ | `year_lookup` が `issue_age=20` ベースに変わるため、**新旧は別 run_id で管理** |

### 5.2 下位互換の確保

`--age-min 40` を明示指定すれば従来通りの結果を再現可能:

```powershell
python -m experience_rate scalebb-fit --age-min 40 ...
```

### 5.3 数値結果への影響

同じ `issue_year` でも `issue_age=40→20` に変更すると `year_lookup`
が変わるため、**同じ出力ファイル名でも中身の値は異なる** 点に注意。

| `issue_age` | age=40 での `year_lookup` (issue_year=2026) | female cancer 40 歳値 |
|---:|---|---:|
| 40 (旧) | 2026 | 33.3 / 10 万 |
| **20 (新)** | **2046** (20 歳加入で 20 年後) | **21.6** / 10 万 |

これは長期改善率 L=1%/年 の 20 年蓄積 (×0.82) + APC 再平滑化効果によるもの。

## 6. パイプライン全体図 (20 歳対応後)

```
[RAW DATA]                                   [20 歳以降のデータを含む]
  EAS/data/RowData/
    ├ estat_processed/vital_statistics/5-15_…csv   (死因×5歳×年)
    ├ estat_processed/patient_survey/Z*.csv
    ├ estat_processed/population/pop_5yr_age_…csv
    └ cancer_incidenceNCR(2016-2023).xls
         ↓
[PANEL BUILD]                                [年齢フィルタ無し = 全年齢保持]
  scripts/build_disease_panel.py
    → data/processed/mortality_apc_panel.parquet
    → data/processed/age_period_panel.parquet
    → data/processed/disease_period_panel.parquet
         ↓
[EAS INCIDENCE LOAD]                         [年齢フィルタ無し]
  EAS/scripts/build_incidence_panel.py
  python -m experience_rate load-incidence
    → population_incidence テーブル
         ↓
[ScaleBB 分析]                              [新 default: age_min=20]
  python -m experience_rate scalebb-apc-fit --use-preset
    → scalebb_improvement (n_age=14)
    → scalebb_cohort_effect (n_cohort=90+)
  python -m experience_rate scalebb-apc-project --use-preset
    → scalebb_projection (rate_projected)
         ↓
[予定発生率テーブル]                         [20-85 歳, 66 単年齢]
  python -m experience_rate scalebb-gen-table --use-preset
    → predicted_rate_generational (issue_age=20)
    → CSV: rate_by_age_M_YYYY_disease_sex.csv

[従来手法 比較]                              [新 default: AGE_MIN=20]
  python scripts/build_traditional_predicted_rates.py
    → predicted_rate_master_traditional.csv (1,188 rows)
```

## 7. 今後の課題

1. **20-29 歳の小標本安定性**: 心疾患・脳血管の死亡率は絶対値
   0.3-5/10 万 と極小。年次変動の影響が大きいため `lam_col=60` に
   引き上げたが、長期検証は継続
2. **若年コホート γ(c) の継続更新**: 2004 年生以降 (観測末端 2024 年で 20 歳)
   の γ は 1 年分のみ。2025-2029 年のデータ反映後に再フィットで安定化
3. **他パイプライン (`rate_type=registry/initial_visit/discharge`) への展開**:
   現状 mortality のみ age_min=20 対応。他 3 系統 (がん登録は 2016-2023
   の短期、患者調査 Z4-4 は 1999-2023 の 9 時点) の拡張は別途検討

## 8. 関連ドキュメント

- [`apc_predicted_rate_tables_by_sex_20260423.md`](./apc_predicted_rate_tables_by_sex_20260423.md)
  — APC 男女別予定率テーブル + 付録 B (20 歳始版)
- [`traditional_predicted_rate_tables_by_sex_20260423.md`](./traditional_predicted_rate_tables_by_sex_20260423.md)
  — 従来手法テーブル + 付録 A (20 歳始版)
- [`methodology_apc_extension_20260422.md`](./methodology_apc_extension_20260422.md)
  — ScaleBB APC 拡張の方法論
- [`validation_scalebb_vs_traditional_20260422.md`](./validation_scalebb_vs_traditional_20260422.md)
  — AP モデル vs 従来手法のバックテスト
