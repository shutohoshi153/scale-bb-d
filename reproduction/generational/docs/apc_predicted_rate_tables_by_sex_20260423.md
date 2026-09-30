**日本語** | [English](apc_predicted_rate_tables_by_sex_20260423.en.md)

# APC 版 男女別 予定疾病発生率テーブル 作成レポート

> **注記（2026-07-16、改題に伴う用語補足）:** 本レポートの「予定疾病発生率テーブル」の実体は、
> 入力＝**死因別死亡率**（人口10万対、`mortality_apc_panel` 由来）から計算した率テーブルである
> （§2「入力データ」参照）。論文（2026-07-15 改題後：*from All-Cause to Cause-Specific Mortality*）
> では、この死因別死亡率を **(i) 医療保険の疾病発生率への代理**、**(ii) 特定疾病死亡保障への
> 対象そのもの（直接のアサンプション）** の二層で用いる。表題・本文の「発生率」表記は製品面の
> 呼称であり、入力・計算は一貫して死因別死亡率（ScaleBB アルゴリズムは入力の意味に非依存で数値は不変）。

- **作成日**: 2026-04-23
- **対象モデル**: Scale BB APC (Age-Period-Cohort) 拡張
- **対象疾病**: cancer / heart_disease / cerebrovascular (3 大死因)
- **対象性別**: male / female (個別フィット)
- **発行年 (issue_year)**: 2024 / 2025 / 2026 / 2027 / 2028
- **契約時年齢 (issue_age)**: 40
- **年齢レンジ**: 40–85 歳 (単年齢、5 歳ビンからの log-linear 補間)
- **投影最終年**: 2100 (40 歳加入者が到達可能な年齢まで網羅)

---

## 1. 目的

本レポートは、`scripts/scale_bb_apc_model.py` で実装した **APC 拡張 Scale BB**
モデルを EAS パイプラインに統合し、**男女別** に予定疾病発生率テーブル
(1D `[age] per (sex, disease, issue_year)`) を生成するまでの工程と結果をまとめる。

APC を採用する動機は、既報
[`methodology_apc_extension_20260422.md`](methodology_apc_extension_20260422.md)
に整理したとおり、以下の 2 点に集約される。

1. **コホート効果の識別**: 出生年 (生年) 由来の罹患傾向 (例: 喫煙習慣・
   生活環境) を Period 効果から分離し、COVID-19 パンデミック前後で
   「何歳のときに曝露したか」の差異を反映する。
2. **下流運用の互換性維持**: APC 拡張によりモデル自体は 3D (sex × age × year)
   化するが、Generational Projection により **下流に配布するのは従来通り
   `[sex, age]` 形式の 1D テーブル** に保つ。

---

## 2. 入力データ

| 項目 | 内容 |
|---|---|
| 元データテーブル | `data/processed/mortality_apc_panel.parquet` |
| 出典 | e-Stat 人口動態統計 (死因別死亡率) |
| 年齢区分 | **5 歳階級** (40–44, 45–49, …, 85–89) — 合計 10 階級 |
| 暦年 | 1950–2024 (5 年刻み、合計 25 年) |
| 性別 | total / male / female |
| 単位 | 人口 10 万対死亡率 |

> **注記**: 5 歳階級が源泉データの制約。予定発生率テーブル側で単年齢に
> 補間 (本レポート Section 5)。

---

## 3. パイプライン全体図

```text
┌──────────────────────────────────────────────────────────────────────┐
│  mortality_apc_panel  (sex × age[5y] × year[5y])                      │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │ ① scalebb-apc-fit
                                 │   (2D WH 平滑化 + 対角罰則 + COVID dummy)
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  scalebb_improvement  +  scalebb_cohort_effect                        │
│    rate_smoothed / improvement_smoothed             γ(cohort)         │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │ ② scalebb-apc-project
                                 │   (改善率 × L ブレンド + コホート外挿)
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  scalebb_projection  (sex × age[5y] × year 1950-2100)                 │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │ ③ scalebb-gen-table --interpolate-age
                                 │   (Generational Projection +
                                 │    log-linear 単年齢補間)
                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│  predicted_rate_generational  (sex × disease × issue_year × age[1y])  │
│  + CSV per (disease, sex, issue_year)                                 │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 4. 作成コマンド (全文再現)

### 4.1 設定プリセット (config.yaml 参照)

| パラメータ | 値 | 意味 |
|---|---|---|
| `lam_row` / `lam_col` / `lam_cohort` | 40.0 / 40.0 / 40.0 | WH 平滑化の罰則 (age / period / cohort) |
| `long_term_rate` | 0.01 | 長期改善率 L (原典 1%) |
| `convergence_year` | 2035 | 改善率が L に収束する年 |
| `horizon_year` | 2100 | 投影最終年 |
| `covid_mode` | `dummy` | COVID 年 (2020-2022) を period shift として分離 |
| `covid_years` | 2020, 2021, 2022 | COVID 対象年 |
| `age_min` / `age_max` | 40 / 85 | 対象年齢レンジ |
| `interpolate_age` | true | 5 歳ビン → 単年齢補間 (log_linear) |

CLI からは `--use-preset` で上記を一括適用 (`config.yaml` の
`scalebb_presets.defaults` + `diseases.<name>` + `sex.<male|female>` を
この順でマージ; 既存 `--lam-row` 等を指定すれば CLI 引数が優先)。

### 4.2 男性パイプライン

```bash
# PYTHONPATH に src を追加 (EAS 直下で実行)
$env:PYTHONPATH = "src"; $env:PYTHONIOENCODING = "utf-8"

# ① APC fit (男性 3 疾病)
python -m experience_rate scalebb-apc-fit `
  --source mortality `
  --sex male `
  --disease cancer heart_disease cerebrovascular `
  --use-preset `
  --run-id male_apc02

# ② APC project (1950-2100 まで投影)
python -m experience_rate scalebb-apc-project `
  --fit ../data/processed/scalebb_apc_fit_male.parquet `
  --use-preset `
  --run-id male_apc02_proj

# ③ Generational Table (発行年 2024-2028, issue_age=40, 単年齢補間)
python -m experience_rate scalebb-gen-table `
  --run-id male_apc02_proj `
  --use-preset `
  --output-dir ../data/processed/predicted_rate_apc
```

### 4.3 女性パイプライン

```bash
python -m experience_rate scalebb-apc-fit `
  --source mortality --sex female `
  --disease cancer heart_disease cerebrovascular `
  --use-preset --run-id female_apc01

python -m experience_rate scalebb-apc-project `
  --fit ../data/processed/scalebb_apc_fit_female.parquet `
  --use-preset --run-id female_apc01_proj

python -m experience_rate scalebb-gen-table `
  --run-id female_apc01_proj --use-preset `
  --output-dir ../data/processed/predicted_rate_apc
```

### 4.4 比較用 AP (従来) パイプライン

APC との対比のため、同じ mortality_apc_panel に対し従来 AP
(`scripts/scale_bb_disease.py`) を同パラメータで実行:

```bash
python -m experience_rate scalebb-fit --source mortality --sex male --age-min 40 --age-max 89 --run-id male01
python -m experience_rate scalebb-project --fit ../data/processed/scalebb_fit.parquet --run-id male01p --horizon 2100
python -m experience_rate scalebb-gen-table --run-id male01p --use-preset

python -m experience_rate scalebb-fit --source mortality --sex female --age-min 40 --age-max 89 --run-id female01
python -m experience_rate scalebb-project --fit ../data/processed/scalebb_fit.parquet --run-id female01p --horizon 2100
python -m experience_rate scalebb-gen-table --run-id female01p --use-preset
```

---

## 5. 単年齢補間 (5 歳ビン → 単年齢)

mortality_apc_panel は 5 歳階級のため、そのままでは
`[sex, age]` 予定率テーブル (契約単位: 単年齢) に使えない。
`scalebb_gen.interpolate_projection_ages()` が下記 3 方式を提供する。

| method | 定義 | 推奨用途 |
|---|---|---|
| `log_linear` (既定) | `log(rate)` を age に対して線形補間 → `exp` | 疾病罹患率 (年齢に対し指数成長) |
| `linear` | `rate` を age に対して線形補間 | 率が概ね線形に変化するケース |
| `log_pchip` | `log(rate)` を単調 PCHIP 補間 | 5 歳刻みの単調性を厳密保持したい場合 |

補間イメージ (male cancer, issue_year=2026, issue_age=40):

| age | 5 歳ビン (source) | log-linear 補間 (output) |
|---:|---:|---:|
| 40 | 20.11 | **20.11** (一致) |
| 41 |  —   | 22.17 |
| 42 |  —   | 24.49 |
| 43 |  —   | 27.12 |
| 44 |  —   | 30.10 |
| 45 | 33.49 | **33.49** (一致) |
| 50 | 58.83 | **58.83** |
| ... | ... | ... |
| 85 | 2218.26 | **2218.26** |

既知点は完全一致、中間年齢は年齢あたり概ね 12–13% ずつ増加する指数成長を再現。

---

## 6. 結果サマリ

### 6.1 DB 格納件数

| run_id | kind | sex | improvement | projection | cohort_effect | generational |
|---|---|---|---:|---:|---:|---:|
| `male_apc02`       | fit | male    | 750 |  0  | **210** |  0  |
| `male_apc02_proj`  | projection | male | 0 | 4,530 | 0 | **690** |
| `female_apc01`     | fit | female  | 750 |  0  | **210** |  0  |
| `female_apc01_proj`| projection | female | 0 | 4,530 | 0 | **690** |
| `male01` / `male01p`     | AP 参照 | male   | 750 / 4,530 | — | — / **690** |
| `female01` / `female01p` | AP 参照 | female | 750 / 4,530 | — | — / **690** |

- improvement: 3 疾病 × 10 ages × 25 years = 750 rows
- projection: 3 × 10 × 151 years = 4,530 rows
- cohort_effect: 3 × 70 cohorts (1865–1984) = 210 rows
- generational: 3 × 5 issue_years × 46 ages = 690 rows (1 男 or 女)

### 6.2 予定発生率 (発行年 2026, issue_age=40, 単年齢補間後)

**3 疾病 × 男女 比較 (人口 10 万対、主要年齢のみ抜粋):**

| age | cancer M | cancer F | heart M | heart F | cerebro M | cerebro F |
|---:|---:|---:|---:|---:|---:|---:|
| 40 |   20.1 |   33.3 |   15.8 |    3.8 |   10.3 |    4.5 |
| 50 |   58.8 |   70.0 |   39.3 |   10.1 |   22.7 |    9.7 |
| 60 |  184.9 |  147.2 |   96.2 |   25.6 |   47.4 |   19.5 |
| 70 |  542.4 |  296.4 |  226.9 |   69.5 |  101.6 |   42.1 |
| 80 | 1405.9 |  575.4 |  537.8 |  214.5 |  228.3 |  103.7 |
| 85 | 2218.3 |  799.9 |  838.2 |  388.6 |  345.7 |  167.4 |

> **読み取り**:
> - がん: 40–50 代は女性 > 男性 (乳がん・子宮頸がんの若年ピーク)、
>   60 代以降は男性 > 女性に逆転。
> - 心疾患・脳血管疾患: 全年齢で男性が約 2–4 倍高い傾向。

### 6.3 APC vs AP 差分 (male cancer, issue_year=2026)

| age | APC | AP (従来) | 差分 |
|---:|---:|---:|---:|
| 40 |   20.1 |   20.9 | **−3.8%** |
| 45 |   33.5 |   35.2 | −4.8% |
| 50 |   58.8 |   60.7 | −3.1% |
| 55 |  104.6 |  104.5 | +0.1% |
| 60 |  184.9 |  177.7 | +4.1% |
| 65 |  321.3 |  296.9 | +8.2% |
| 70 |  542.4 |  485.7 | +11.7% |
| 75 |  884.6 |  778.0 | +13.7% |
| 80 | 1405.9 | 1228.5 | **+14.4%** |
| 85 | 2218.3 | 1926.2 | **+15.2%** |

**解釈**:

- 若年 (40 代): APC がわずかに低い (最近コホートの相対率低下傾向を反映)
- 高齢 (70–85): **APC が AP より 12–15% 高い** — 近代コホート (1950–1970 生)
  は戦前世代より喫煙歴・生活習慣リスクが高く、γ(c) が正にシフト。AP では
  これが period 効果に吸収されていたが、APC は明示的に γ として分離する。

### 6.4 コホート効果 γ(cohort) 抜粋 (cancer)

| cohort (出生年) | male γ | female γ | 備考 |
|---:|---:|---:|---|
| 1870 | −1.23 | −0.89 | 明治初期 (基準水準マイナス) |
| 1890 | −0.28 | −0.15 | 明治後期 |
| 1910 | +0.18 | +0.16 | 大正期 (ピーク前) |
| **1930** | **+0.27** | **+0.16** | **がんリスク最大コホート** |
| 1950 | +0.07 | −0.00 | 団塊世代、低下開始 |
| 1970 | −0.39 | −0.25 | 禁煙運動・生活様式改善 |
| 1980 | −0.73 | −0.40 | 低リスクコホート |
| 1984 | −0.77 | −0.40 | 観測末端 |

男性は γ の振幅が女性より大きく (戦前世代から 1930 年生までの上昇が顕著)、
1930 年生まれをピークに 1984 年生まれでは −0.77 (≒ exp(−0.77) = 46% 相対)
まで低下。これは日本人男性の喫煙率減少・胃がん減少と整合する。

---

## 7. 出力ファイル一覧

### 7.1 中間成果物 (DB 入力用 parquet/CSV)

```text
data/processed/
├── scalebb_apc_fit_male.parquet        (750 rows; rate_smoothed 等)
├── scalebb_apc_fit_male.csv
├── scalebb_apc_fit_male.cohort.csv     (210 rows; γ(cohort))
├── scalebb_apc_fit_male.meta.json      (APC config)
├── scalebb_apc_fit_female.parquet
├── scalebb_apc_fit_female.cohort.csv
├── scalebb_apc_projection_male.parquet   (4,530 rows; rate_projected 1950-2100)
├── scalebb_apc_projection_male.csv
└── scalebb_apc_projection_female.parquet
```

### 7.2 配布用 予定発生率テーブル (APC)

格納先: `data/processed/predicted_rate_apc/`

| ファイル名パターン | 行数 | 内容 |
|---|---:|---|
| `predicted_rate_cancer_male_issue{YYYY}_ia40.csv`         | 46 | 男性・がん・各発行年 (40–85 歳) |
| `predicted_rate_cancer_female_issue{YYYY}_ia40.csv`       | 46 | 女性・がん |
| `predicted_rate_heart_disease_male_issue{YYYY}_ia40.csv`  | 46 | 男性・心疾患 |
| `predicted_rate_heart_disease_female_issue{YYYY}_ia40.csv`| 46 | 女性・心疾患 |
| `predicted_rate_cerebrovascular_male_issue{YYYY}_ia40.csv`| 46 | 男性・脳血管 |
| `predicted_rate_cerebrovascular_female_issue{YYYY}_ia40.csv`| 46 | 女性・脳血管 |

各発行年 {2024,2025,2026,2027,2028} × 3 疾病 × 2 性別 = **30 ファイル** +
マスター CSV 2 本 (male_apc, female_a)。各ファイルは

```csv
age,rate_per_100k
40,20.11460760300782
41,22.16528217233873
42,24.487563508215846
...
85,2218.2630148017143
```

の 2 列 × 46 行。`year_lookup = issue_year + (age − issue_age)` で
将来投影年を復元可能。

### 7.3 DB テーブル

```sql
-- APC 拡張で追加
scalebb_cohort_effect
  run_id TEXT, disease_id TEXT, sex TEXT, section TEXT,
  cohort INTEGER, gamma REAL, is_observed INTEGER
  PRIMARY KEY (run_id, disease_id, sex, section, cohort)

-- 既存 (AP と共通)
predicted_rate_generational
  run_id, disease_id, sex, section,
  issue_year, issue_age, age, rate_per_100k, year_lookup
```

---

## 8. 運用指針

### 8.1 推奨プリセット適用方針

`config.yaml` の `scalebb_presets` を利用することで、以下が自動化される。

- COVID 期 (2020-2022) の扱い: **`dummy` モード** (β shift として分離)
- 平滑化パラメータ λ: 40.0 (ICP (incidence curve plot) の滑らかさが
  確保できる値として原典踏襲)
- 脳血管疾患の `lam_cohort` は 20.0 に引き下げ — 戦前世代からの急速な
  死亡率低下により、コホート方向の曲率が強く、罰則を弱める必要がある

### 8.2 更新頻度

| 更新タイミング | 対象 | 方法 |
|---|---|---|
| 年次 (e-Stat 公表後) | mortality_apc_panel を +1 年 | `build_disease_panel.py` 再実行後 APC fit |
| 年次 | γ(c) 再推計 | `scalebb-apc-fit` 再実行 |
| 年次 | 予定率テーブル再発行 | `scalebb-apc-project` + `scalebb-gen-table` |
| 発行年ごと | 契約発行年に応じた専用テーブル | `--issue-years <yr>` で追加生成 |

### 8.3 単年齢補間の注意点

- `log_linear` は滑らかだが、5 歳ビン内に疾病プロファイルの屈曲 (例:
  女性がんの 45-55 乳がんピーク) があると真値からずれる可能性
- 契約設計では本 5 歳バンドル内の平均誤差が許容範囲かバリデーションが必要
- 将来 e-Stat が単年齢を公開した場合、`--no-interpolate-age` で直接利用

---

## 9. 関連ドキュメント

- [APC 拡張手法書](methodology_apc_extension_20260422.md) — 数式定式化・識別性
- [従来手法との比較検証](validation_scalebb_vs_traditional_20260422.md) — AP 版 vs 伝統手法
- `EAS/README.md` — CLI 全般リファレンス
- `EAS/docs/Scale_BB機能.md` — DB スキーマ詳細

---

## 付録 A: 実行ログ (要約)

```
[apc-fit] disease=cancer sex=male section=total n_age=10 n_year=25
         year_range=1950-2024 covid_mode=dummy
[apc-fit] disease=heart_disease sex=male section=total ...
[apc-fit] disease=cerebrovascular sex=male section=total ...
[apc-load] scalebb_improvement=750 rows, scalebb_cohort_effect=210 rows
           (run_id=male_apc02)

[apc-project] disease=cancer sex=male project_years=1950-2100
[apc-load] scalebb_projection=4530 rows (run_id=male_apc02_proj)

[interpolate] method=log_linear rows: 4530 → 20286
[scalebb-gen-table] rows_loaded = 690   files_written = 15
                    interpolate_age = True (log_linear)
```

(female 側も同一パターン。)

---

## 付録 B: 20 歳始拡張版 (2026-04-23 追記)

### B.1 背景・動機

従来 40 歳以降をターゲットとしていたが、**若年層向け医療保険商品・学資保険**
への適用を想定し、分析開始年齢を **20 歳** に拡張した。mortality_apc_panel は
20-24 歳から連続しており (Section 2)、追加で 4 階級 (20-24, 25-29, 30-34, 35-39)
を取り込む。

### B.2 設定変更 (`config.yaml`)

```yaml
scalebb_presets:
  defaults:
    age_min: 20           # 40 → 20
    age_max: 85
    lam_col: 60.0         # 40.0 → 60.0 (若年ノイズ抑制のため強化)
  generational:
    issue_age: 20         # 40 → 20
    age_min: 20           # 40 → 20
    age_max: 85
```

`lam_col` を 40→60 に強化したのは、20-30 代の死亡率が絶対値として小さく
(例: 男性脳血管 20-24 歳 ≒ 0.45/10 万)、年次の統計的変動が相対的に
大きいため (ポアソン的な小標本効果)。

### B.3 実行 (男女 × 3 疾病)

```bash
$env:PYTHONPATH = "src"; $env:PYTHONIOENCODING = "utf-8"

# 男性
python -m experience_rate scalebb-apc-fit --sex male --use-preset --run-id male_apc03_age20
python -m experience_rate scalebb-apc-project --fit ../data/processed/scalebb_apc_fit_male.parquet `
  --use-preset --run-id male_apc03_age20_proj
python -m experience_rate scalebb-gen-table --run-id male_apc03_age20_proj --use-preset `
  --output-dir ../data/processed/predicted_rate_apc_age20

# 女性
python -m experience_rate scalebb-apc-fit --sex female --use-preset --run-id female_apc02_age20
python -m experience_rate scalebb-apc-project --fit ../data/processed/scalebb_apc_fit_female.parquet `
  --use-preset --run-id female_apc02_age20_proj
python -m experience_rate scalebb-gen-table --run-id female_apc02_age20_proj --use-preset `
  --output-dir ../data/processed/predicted_rate_apc_age20
```

### B.4 DB 格納件数 (拡張後)

| run_id | kind | n_age | improvement | projection | cohort_effect | generational |
|---|---|---:|---:|---:|---:|---:|
| `male_apc03_age20`       | fit | **14** | 1,050 | — | **270** | — |
| `male_apc03_age20_proj`  | projection | 14 | — | 6,342 | — | **990** |
| `female_apc02_age20`     | fit | **14** | 1,050 | — | **270** | — |
| `female_apc02_age20_proj`| projection | 14 | — | 6,342 | — | **990** |

- n_age: 10→**14** (20-24 ~ 85-89 の 14 階級)
- cohort_effect: 210→**270** (1985-2004 生の若年コホート追加)
- generational: 690→**990** (5 発行年 × 3 疾病 × **66 ages**=20-85)

### B.5 若年層予定率 (APC, 発行年 2026, **加入 20 歳**)

#### 男女 × 3 疾病 × 主要若年齢 (人口 10 万対)

| age | cancer M | cancer F | heart M | heart F | cerebro M | cerebro F |
|---:|---:|---:|---:|---:|---:|---:|
| 20 |  2.38 |  2.31 | 1.66 | 0.76 | 0.45 | 0.30 |
| 25 |  3.80 |  3.93 | 2.58 | 1.19 | 0.81 | 0.48 |
| 30 |  6.02 |  6.91 | 4.19 | 1.81 | 1.62 | 0.92 |
| 35 |  9.66 | 12.28 | 6.86 | 2.59 | 3.25 | 1.68 |
| 40 | 15.84 | 21.60 |11.25 | 3.73 | 6.28 | 2.84 |

**観察**:

- **20-24 歳**: がんは男女ほぼ同水準 (~2.3/10 万)、脳血管は男 1.5 倍女性
- **25-35 歳**: **女性がんが男性を上回る** (乳がん・子宮頸がんの若年ピーク)
- **35 歳付近で逆転**: 40 歳以降は男性のほうが高い (既報と整合)

### B.6 若年コホート γ(c) 効果 — 新規発見

1985-2004 年生の 4 コホートについて、APC により γ が新規に推定された。

| cohort | disease | male γ | female γ | 解釈 |
|---:|---|---:|---:|---|
| 1990 | cancer | −0.30 | −0.27 | 同水準の低リスク |
| 2004 | cancer | −0.29 | **−0.61** | **若年女性の継続的低下** |
| 1990 | cerebrovascular | +0.16 | +0.23 | 若年脳血管やや高め |
| 2004 | cerebrovascular | +0.12 | **+0.41** | **若年女性脳血管リスク上昇** |
| 1990 | heart_disease | −0.11 | −0.22 | 男女とも低下 |
| 2004 | heart_disease | −0.31 | +0.04 | 男は継続低下、**女は反転** |

**注目点**:

1. **若年女性がんの γ 継続低下** (−0.27 → −0.61 相当で exp⁻¹ = 45%): 検診普及・
   子宮頸がんワクチン・喫煙率低下の寄与を示唆
2. **若年女性の脳血管 γ 上昇** (+0.23 → +0.41): 最近の世代ほど相対リスクが
   増大 — 肥満率・運動不足・高血圧の若年化が仮説要因
3. **若年女性心疾患 γ が 2004 年生で反転** (−0.22 → +0.04): 長らく低下して
   いたトレンドが若年世代で止まった可能性 (統計的識別の安定性要検証)

これらは 40 歳始の従来 APC では **観測不可能な世代効果**であり、
若年コホート情報を取り込むことで新たな知見を得られた。

### B.7 Generational Projection の `year_lookup` 変化

**重要**: `issue_age=40→20` に変更すると、同じ `age=40` でも `year_lookup`
が変化するため値が変わる (バグではない)。

| issue_age | age=40 の year_lookup (発行年 2026) | female cancer 値 |
|---:|---|---:|
| 40 (旧) | 2026 (契約年そのもの) | 33.3 |
| **20 (新)** | **2046** (20 歳加入者が 40 歳到達時) | **21.6** |

year_lookup が 20 年未来 = 長期改善率 L=1%/年 の蓄積で
`(1 − 0.01)^20 ≒ 0.82` ≒ 18% 下方シフト。加えて APC 投影の年齢プロファイル
再平滑化の効果が重なる。

### B.8 出力物 (age20 版)

- `data/processed/predicted_rate_apc_age20/` - 30 CSV × 66 ages
- `data/processed/scalebb_apc_fit_male.parquet` - 1,050 rows
- `data/processed/scalebb_apc_projection_male.parquet` - 6,342 rows
- `data/processed/scalebb_apc_fit_male.cohort.csv` - 270 rows (70→90 cohorts)
- female も同一構造

### B.9 今後の課題

1. **小標本安定性**: 20-24 歳死亡率はポアソン変動が大きい。数値的安定化のため
   `lam_col=60` に引き上げたが、**20-29 歳の観測年次変動** を ICI (inter-cohort
   interval) 系の別指標でクロスチェックすべき
2. **若年コホート数不足**: 2004 年生の γ は観測期間末端 (20 歳到達 = 2024 年)
   のため、実質 1 年分のデータのみ。2025-2029 年のデータが入ると γ(c) 推定が
   安定する
3. **疾病発生率との対比**: `EAS/data/RowData/cancer_incidenceNCR(2016-2023).xls`
   (がん登録データ) を併用し、**死亡率ベース** と **罹患率ベース** の
   予定率乖離を定量化する拡張を別途検討
