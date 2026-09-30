**日本語** | [English](estat_data_dictionary.en.md)

# e-Stat API 取得データ辞書

本研究「Scale BB 思想の疾病発生率への応用」で使用する、e-Stat API から取得した全データセットの構造・コード体系・使い方を記述する。

- 最終更新: 2026-04-22
- 取得元: e-Stat API v3.0 (<https://www.e-stat.go.jp/api/>)
- 関連スクリプト: `scripts/estat_api_client.py` 他

---

## 1. 概観

### 1.1 ディレクトリ構造

```text
RowData/
  estat_api/                      # API から取得した原 JSON（キャッシュ）
    getStatsList/                 # 統計表検索結果
    getMetaInfo/                  # メタ情報（本取得では未使用）
    getStatsData/                 # 統計データ本体（statsDataId ごと）
    stats_list_summary_*.csv      # 3統計の表一覧サマリ（4,239表）
    priority_tables_patient_survey.csv  # 本研究用 30 表の選抜
  estat_processed/                # long-CSV 化済みデータ
    patient_survey/               # 患者調査 30 表
      _manifest.csv
      Z{XX}__{statsDataId}.csv
    population/                   # 人口推計 (結合済)
      pop_5yr_age_combined.csv    ← メイン
      pop_5yr_age_series{A-G}__*.csv  (結合前の原発行版)
    vital_statistics/             # 人口動態 6 表
      5-{XX}_*__{statsDataId}.csv
```

### 1.2 共通カラム規約

long-CSV 変換後、全ファイルで以下のカラムが付く：

| カラム | 型 | 役割 |
|---|---|---|
| `<軸名>_code` | int/str | e-Stat 内部コード |
| `<軸名>` | str | 軸コードに対応する日本語ラベル |
| `unit` | str | 単位（例：`千人`、`人口10万対`、`人`） |
| `value_raw` | str/num | API レスポンスの `$` 生文字列 |
| `value` | float | `value_raw` を数値化（欠測は NaN） |

軸名は e-Stat 側の `CLASS_INF/@name` が採用され、テーブルごとに微妙に異なる（例：`年齢階級` / `年齢階級_004` / `年齢階級_006`）。後続の分析で統一する場合は `scripts/estat_stats_data_to_long.py` を拡張するか、読込側で rename する。

### 1.3 欠測・記号の扱い

| 記号 | 意味 | value での扱い |
|---|---|---|
| `-` | 該当なし | NaN |
| `…` | 調査対象外 | NaN |
| `※` | 国勢調査確定人口で再計算済 | 数値化（注記のみ） |
| 空文字 | 欠測 | NaN |

---

## 2. 患者調査 (Patient Survey, statsCode=00450022)

### 2.1 収録テーブル一覧

| titleNo | statsDataId | 用途 | 行数 | 主軸 |
|---|---|---|---|---|
| **Z2-4** | 0004025884 | 患者数 時系列 (H11-R5) | 675 | 性×年齢×年次 |
| **Z3-2** | 0004025886 | 患者数 時系列 (H8-R5, 傷病別) | 1,800 | 傷病×入院外来×年次 |
| **Z4-4** | 0004025890 | 受療率 時系列 (H11-R5) | 675 | 性×年齢×年次 |
| **Z5-2** | 0004025892 | 受療率 時系列 (H8-R5, 傷病別) | 1,800 | 傷病×入院外来×年次 |
| Z2-1〜Z2-3 | - | 患者数 時系列 (昭和30-H8) | 過去データ | |
| Z3-1 | 0004025885 | 患者数 時系列 (S54-H5, 傷病別) | 1,566 | |
| Z4-1〜Z4-3 | - | 受療率 時系列 (昭和30-H8) | 過去データ | |
| Z5-1 | 0004025891 | 受療率 時系列 (S54-H5, 傷病別) | 1,566 | |
| **Z9** | 0004025899 | 患者数 (R5 断面) | 13,500 | 傷病×年齢×性×施設 |
| Z10, Z11 | 0004025900/1 | 入院/外来患者数 | 13,500 / 40,500 | |
| Z12, Z13 | 0004025902/3 | 患者数 (傷病大/中分類) | 各 7,500-90,000 | |
| Z14, Z15 | 0004025904/5 | 入院/外来 (小分類) | 50,250 | |
| **Z68** | 0004025961 | **受療率 断面 (5歳×傷病)** | 4,320 | 傷病×年齢×性 |
| Z69 | 0004025962 | 入院受療率 断面 | 4,320 | |
| Z70 | 0004025963 | 外来受療率 断面 | 12,960 | ×初診/再来 |
| Z71 | 0004025964 | 受療率 (大分類) | 32,040 | |
| **Z72** | 0004025965 | **受療率 (中分類)** | 53,280 | |
| Z73 | 0004025966 | 受療率 (小分類) | 133,560 | 最大粒度 |
| Z156-Z160 | 4026062-6 | 総患者数 | 各 4,000-24,000 | 大/中/小/基本分類 |

太字は Scale BB 適用時の中核テーブル。

### 2.2 表章項目コード

| code | 表章項目 | 単位 |
|---|---|---|
| 9 | 受療率（人口10万対） | 対10万人 |
| 10 | 受療率（人口10万対）の年次推移 | 対10万人 |
| 14 | 推計外来患者数 | 千人 |
| 16 | 推計患者数 | 千人 |
| 22 | 推計患者数の年次推移 | 千人 |
| 29 | 推計入院患者数 | 千人 |
| 38 | 総患者数 | 千人 |
| 45 | 入院受療率（人口10万対） | 対10万人 |

### 2.3 傷病分類軸（要注意）

患者調査の傷病分類軸は **ローマ数字（Ⅰ〜XXII）接頭辞を含まない** ことに注意：

```
APIレスポンス:  '新生物＜腫瘍＞'
過去のTXT資料: 'Ⅱ　新生物＜腫瘍＞'
```

再掲項目は先頭に U+3000（全角スペース）が付く：

```
'　（悪性新生物＜腫瘍＞）（再掲）'  # ← U+3000 プレフィックス
```

テーブルにより `傷病分類`, `傷病分類２`, `傷病分類_004`, `傷病大分類`, `傷病中分類`, `傷病小分類` 等に分岐。粒度の目安：

| 軸 | 値の数 | 例 |
|---|---|---|
| 傷病分類/傷病分類２ | 約 22-60 | Ⅰ〜XXII 大分類 + 再掲 |
| 傷病大分類 | 約 5-14 | 大分類のみ |
| 傷病中分類 | 約 130-180 | 中分類 |
| 傷病小分類 | 約 400-700 | 小分類 |
| 傷病基本分類 | 約 5,000 | ICD-10 3桁詳細 |

### 2.4 年齢階級軸

通常 5歳階級で 22-25 区分。コード体系例：

```
1    総数
1001 0歳
1002 1-4歳
1003 5-9歳
...
1022 90歳以上
2001 (再掲) 65歳以上
```

### 2.5 時間軸

| 軸名 | 収録年 |
|---|---|
| `年次30-40` (Z2-1, Z4-1) | 昭和30, 35, 40年 |
| `年次45-58` (Z2-2, Z4-2) | 昭和45, 50, 54, 56, 58年 |
| `年次59-H8` (Z2-3, Z4-3) | 昭和59, 62, 平成2, 5, 8年 |
| `年次11－29` (Z2-4, Z4-4) | 平成11, 14, 17, 20, 23, 26, 29, 令和2, 令和5年 |
| `年次54-H5` (Z3-1, Z5-1) | 昭和54, 56, 59, 62, 平成2, 5年 |
| **`年次8－29` (Z3-2, Z5-2)** | **平成8, 11, 14, 17, 20, 23, 26, 29, 令和2, 令和5年** |

本研究の中心は `年次8－29`（1996-2023年の10時点）。

### 2.6 単位・換算

- 患者数系: `千人` → 実数に戻すには `value * 1000`
- 受療率系: 人口10万人対 → 実数に戻すには `value * 人口 / 100000`

---

## 3. 人口推計 (Population Estimates, statsCode=00200524)

### 3.1 統合ファイル

**メインデータ: `RowData/estat_processed/population/pop_5yr_age_combined.csv`**

| 項目 | 内容 |
|---|---|
| 行数 | 2,643 |
| 年カバレッジ | 1980, 1985, 1990, 1995-2024 (**33年、1995以降は全年連続**) |
| 年齢区分 | 22 (+ 5 再掲) = 27 |
| 性別 | 男女計 / 男 / 女 |
| 地域 | 全国のみ |
| 単位 | 千人 (人口) または ％ (割合) |

7つの発行版 (seriesA-G) から重複除去・最新版優先で統合。統合ロジックは `scripts/combine_population.py`。

### 3.2 主要カラム

| カラム | 例 | 備考 |
|---|---|---|
| `時間軸（年）` | `2020年` | 各年10月1日現在 |
| `年齢5歳階級` | `0～4歳`, `65～69歳`, `（再掲）65歳以上` | 5年刻み + 再掲 |
| `男女別` | `男女計` / `男` / `女` | |
| `人口・割合` | `人口` / `割合` | seriesB-G で併存。分析時は `人口` にフィルタ |
| `value` | 127095 | 千人単位 |
| `source` | `pop_5yr_age_seriesB__...` | 由来の発行版 |

### 3.3 分析での使い方

```python
import pandas as pd

pop = pd.read_csv("RowData/estat_processed/population/pop_5yr_age_combined.csv")
# 人口のみ抽出（seriesB-G には割合も混ざる）
pop = pop[(pop["人口・割合"].isna()) | (pop["人口・割合"] == "人口")]
# 男女計のみ、再掲を除外
pop = pop[pop["男女別"] == "男女計"]
pop = pop[~pop["年齢5歳階級"].str.contains("再掲", na=False)]
# 患者調査の年と整合させる
target_years = ["1996年", "1999年", "2002年", "2005年", "2008年",
                "2011年", "2014年", "2017年", "2020年", "2023年"]
pop = pop[pop["時間軸（年）"].isin(target_years)]
```

### 3.4 既知のギャップ

- **1981-1984, 1986-1989, 1991-1994 年は欠損**（5年刻みのみ）
  - 不要: 患者調査は3年刻みかつ1996年以降が主対象のため影響なし
- 1996-2024 の全年は連続取得済 → 患者調査10時点すべての分母が揃う

---

## 4. 人口動態統計 (Vital Statistics, statsCode=00450011)

### 4.1 収録テーブル一覧

| ファイル | statsDataId | 行数 | 主軸 | Pri |
|---|---|---|---|---|
| `5-15_死因_性_5歳階級_年次_死亡数率__0003411659.csv` | 0003411659 | 57,375 | 死因×年齢×性×年×死亡数/率 | **1** |
| `5-25_悪性新生物_性_5歳階級_年次_死亡率__0003411669.csv` | 0003411669 | 8,800 | がん特化×年齢×性×年 | 1 |
| `5-28_心疾患_性_年次_死亡数率__0003464100.csv` | 0003464100 | 2,728 | 心疾患×性×年×4指標 | 1 |
| `5-27_脳血管_性_年次_死亡数率__0003464099.csv` | 0003464099 | 1,364 | 脳血管×性×年×4指標 | 1 |
| `5-12_死因_性_年次_死亡数率__0003411656.csv` | 0003411656 | 12,546 | 死因×性×年 (**1899年-**) | 2 |
| `5-26_悪性新生物_性_年次_年齢調整死亡率__0003464098.csv` | 0003464098 | 1,240 | がんサブカテゴリ×性×年 | 2 |

### 4.2 死因年次推移分類（5-15, 5-12 で使用）

| code | 名称 | Scale BB 関連疾病 |
|---|---|---|
| `Hi00` | 総数 | |
| `Hi01` | 結核 | |
| **`Hi02`** | **悪性新生物＜腫瘍＞** | **研究コア** |
| `Hi03` | 糖尿病 | |
| `Hi04` | 高血圧性疾患 | |
| **`Hi05`** | **心疾患（高血圧性を除く）** | **研究コア** |
| **`Hi06`** | **脳血管疾患** | **研究コア** |
| `Hi07` | 肺炎 | |
| `Hi08` | 慢性気管支炎及び肺気腫 | |
| `Hi09` | 喘息 | |
| `Hi10` | 胃潰瘍及び十二指腸潰瘍 | |
| `Hi11` | 肝疾患 | |
| `Hi12` | 腎不全 | |
| `Hi13` | 老衰 | |
| `Hi14` | 不慮の事故 | |
| `Hi15` | (再掲) 交通事故 | |
| `Hi16` | 自殺 | |

### 4.3 時間軸

- 5-15 / 5-25: 25年（1950, 1960, 1970, 1980, 1990, 2000, 2005, 2010, 2015, 2018-2024）
- 5-27 / 5-28: 31年（1995-2024 連続 + α）
- 5-12 / 5-26: **123年 / 31年**（5-12 は 1899-2024 の超長期）

### 4.4 表章項目（5-27, 5-28 で複数含む）

| code | 表章項目 | 単位 |
|---|---|---|
| 10100 | 死亡数 | 人 |
| 10110 | 死亡率 | 人口10万対 |
| 10120 | 年齢調整死亡率（平成27年モデル人口） | 人口10万対 |
| 10130 | 百分率 | ％ |

---

## 5. 典型的な分析レシピ

### 5.1 受療率 → 実患者数 への換算

```python
import pandas as pd

# 受療率（人口10万対、傷病×年×入院外来）
rates = pd.read_csv("RowData/estat_processed/patient_survey/Z5-2__0004025892.csv")
# 人口（全年代総数）
pop = pd.read_csv("RowData/estat_processed/population/pop_5yr_age_combined.csv")
pop = pop[(pop["男女別"] == "男女計") & (pop["年齢5歳階級"] == "総数")]
pop = pop[(pop["人口・割合"].isna()) | (pop["人口・割合"] == "人口")]
pop["year"] = pop["時間軸（年）"].str.replace("年", "").astype(int)

# 和暦→西暦
era_map = {f"平成{n}年": 1988 + n for n in range(1, 32)}
era_map.update({f"令和{n}年": 2018 + n for n in range(1, 7)})
rates["year"] = rates["年次8－29"].map(era_map)

# 結合して実数化
merged = rates.merge(pop[["year", "value"]].rename(columns={"value": "pop_thousand"}),
                     on="year")
merged["患者数"] = merged["value"] * merged["pop_thousand"] * 1000 / 100000
```

### 5.2 Scale BB 改善率ヒートマップ用のデータ

```python
# Z4-4 (受療率、年齢×年) を年齢×暦年の行列に
rates = pd.read_csv("RowData/estat_processed/patient_survey/Z4-4__0004025890.csv")
rates = rates[rates["表側4－4－23表"].str.contains("総数・")]  # 入院/外来は別途絞る
# ピボット化 → Scale BB の heatmap 適用対象
matrix = rates.pivot_table(index="表側4－4－23表", columns="年次11－29", values="value")
```

### 5.3 死亡率と患者数のクロスバリデーション

```python
# 疾病: 悪性新生物 ↔ がん受療率 の相関確認
mortality = pd.read_csv("RowData/estat_processed/vital_statistics/5-15_死因_性_5歳階級_年次_死亡数率__0003411659.csv")
mortality = mortality[mortality["死因年次推移分類_code"] == "Hi02"]
# 患者調査側の「新生物＜腫瘍＞」と突き合わせて相関係数等を計算
```

---

## 6. 再取得・更新の手順

```powershell
# 1. 統計表一覧を更新（新テーブルが公開された場合）
python scripts/fetch_estat_stats_list.py

# 2. 患者調査30表を再取得
python scripts/bulk_fetch_patient_survey.py

# 3. 人口を再取得・統合
python scripts/fetch_population_data.py
python scripts/combine_population.py

# 4. 人口動態を再取得
python scripts/fetch_vital_stats_data.py
```

全スクリプトはキャッシュにより2回目以降は高速化される（同一 statsDataId は再ダウンロードしない）。再ダウンロードを強制したい場合はクライアント初期化時に `use_cache=False` を指定。

---

## 7. トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| `statsDataId=[xxx]のデータは存在しません` | ゼロパディング抜け | 10桁 `zfill(10)` を適用 |
| カテゴリ名が TXT と一致しない | ローマ数字接頭辞差 / U+3000 差 | `scripts/verify_estat_full_comparison.py` の `normalize_category` を流用 |
| `value` が NaN | 原データが `-` / `…` | `.dropna(subset=["value"])` |
| 文字化け (Windows PowerShell) | `cp1252` コーデック | `$env:PYTHONIOENCODING = "utf-8"` を設定 |

---

## 8. 参考資料

- e-Stat API v3.0 公式: <https://www.e-stat.go.jp/api/api-info/e-stat-manual3-0>
- 患者調査 (厚労省): <https://www.mhlw.go.jp/toukei/list/10-20.html>
- 人口推計 (総務省統計局): <https://www.stat.go.jp/data/jinsui/>
- 人口動態統計 (厚労省): <https://www.mhlw.go.jp/toukei/list/81-1a.html>
- Scale BB 原著 (SOA, 2012): `PDF/researchmortalityimprovebbreport.pdf`

---

## 付録: 生成されたサマリ CSV

| ファイル | 用途 |
|---|---|
| `RowData/estat_api/stats_list_summary_all.csv` | 4,239 テーブル全一覧 |
| `RowData/estat_api/priority_tables_patient_survey.csv` | 優先 30 表の抽出 |
| `RowData/estat_processed/patient_survey/_manifest.csv` | 取得結果・行数 |
| `RowData/estat_processed/population/_manifest.csv` | 人口7発行版の取得結果 |
| `RowData/estat_processed/vital_statistics/_manifest.csv` | 人口動態6表の取得結果 |
| `RowData/estat_processed/Z5-2_api_vs_txt.csv` | API vs 手動DL 全量一致検証 |

---

## 9. タスク A 成果物: 統合パネル (`data/processed/`)

`scripts/build_disease_panel.py` により 4 つの tidy パネルが生成される（parquet と
CSV を並行出力）。Scale BB 適用のすべての後続タスク (B 可視化 / C モデル実装) は
原則としてこれらを入力とする。

### 9.1 共通正規化規約

`scripts/panel_helpers.py` が以下を提供:

| 関数 | 役割 |
|---|---|
| `wareki_to_seireki` | 「平成8年 / 令和元年 / ２０２３年 / 1995年」→ 1996 / 2019 / 2023 / 1995 |
| `parse_age_label` | 年齢ラベル（全角数字・全角チルダ・再掲・総数）→ `AgeBand(code, low, high, is_recap, is_total)` |
| `normalize_disease_label` | ローマ数字/数字接頭辞除去・Z68 階層 `大分類(内訳(再掲))` の内訳採用・再掲トレーラ除去・外側括弧除去 |
| `focus_disease_id` | 3 疾病 + 参考カテゴリの統一 ID に写像（下表） |
| `load_population` | `pop_5yr_age_combined.csv` を tidy 読込（sex を `total/male/female` に正規化） |

統一 disease_id:

| disease_id | 対応範囲 | 備考 |
|---|---|---|
| `cancer` | 悪性新生物＜腫瘍＞ | 患者調査 / 人口動態 (Hi02 / Hi022017) 共通 |
| `neoplasm_all` | 新生物＜腫瘍＞（良性含む大分類） | 患者調査のみ |
| `cardiovascular_all` | 循環器系の疾患（大分類） | 患者調査のみ |
| `heart_disease` | 心疾患（高血圧性を除く） | 患者調査（再掲）/ 人口動態 (Hi05) |
| `ischemic_heart` | 虚血性心疾患（再掲） | 患者調査のみ |
| `cerebrovascular` | 脳血管疾患 | 患者調査（再掲）/ 人口動態 (Hi06) |
| `hypertensive` | 高血圧性疾患 | 患者調査（再掲）/ 人口動態 (Hi04 / Hi042017) |
| `total` | 総数 | 人口動態 (Hi00) のみ |

年齢コード（`age_code`）:

| 例 | 意味 |
|---|---|
| `total` | 全年齢計 |
| `a00_04`, `a05_09`, ..., `a85_89`, `a90_94`, `a95_99` | 5 歳階級 |
| `a90p`, `a100p` | 開区間上限 |
| `r65p`, `r75p`, `r15_64`, `r65_74` | 再掲集計 |
| `a00`, `a01_04` | Z68/Z72 のみ存在する未満 5 歳の細分 |

### 9.2 `disease_period_panel.parquet` / `disease_panel.parquet`

- **入力**: `Z5-2__0004025892.csv` (受療率) ＋ `Z3-2__0004025886.csv` (推計患者数) ＋ 人口総計
- **行数**: 1,800
- **主キー**: (`disease_norm`, `section`, `year`)
- **年範囲**: 1996, 1999, 2002, 2005, 2008, 2011, 2014, 2017, 2020, 2023 (10 時点)
- **section**: `total` / `inpatient` / `outpatient`
- **カラム**:

| カラム | 説明 |
|---|---|
| `disease_id` | 3 疾病共通 ID（NaN の行も多い。disease_norm を使う場合あり） |
| `disease_norm` | 正規化された日本語疾病名 |
| `disease_is_recap` | 再掲項目フラグ |
| `disease_raw` | API レスポンスそのまま |
| `section` | ordered category: total < inpatient < outpatient |
| `year` | 西暦 |
| `rate_per_100k` | 受療率（人口 10 万対） |
| `patients_thousand` | Z3-2 由来の推計患者数（千人） |
| `patients_estimated_thousand` | rate × 総人口 / 100,000（千人単位） |
| `population_total_thousand` | 当年 10 月 1 日 男女計総数人口（千人） |

**検証**: `patients_estimated` と `patients_thousand` は ±0.2% 以内で一致（東日本大震災で一部県が
除外された 2011 年のみ約 1.9% 差）。

`disease_panel.parquet` はこのファイルの別名（引き継ぎプロンプトで指定されたメイン成果物）。

### 9.3 `age_period_panel.parquet`

- **入力**: `Z4-4__0004025890.csv`（全疾病合算の年齢×性×年受療率）＋ 人口
- **行数**: 675
- **主キー**: (`section`, `sex`, `age_code`, `year`)
- **年範囲**: 1999, 2002, 2005, 2008, 2011, 2014, 2017, 2020, 2023 (9 時点)
- **粒度**: 5 歳階級 20 区分 + 総数 / 男 / 女 + 65 歳以上 / 70 歳以上 再掲
- **カラム**: `section, sex, age_code, age_label, age_low, age_high, age_is_recap,
  age_is_total, year, rate_per_100k, population_thousand, patients_estimated_thousand`

### 9.4 `age_disease_2023_panel.parquet`

- **入力**: `Z68__0004025961.csv`（大分類 × 5 歳階級 × 性, 2023 断面）＋ 2023 人口
- **行数**: 4,320
- **主キー**: (`disease_norm`, `sex`, `age_code`)
- **制限事項**:
  - `section` は `total` のみ（Z68 自身に入院外来区分が無い。詳細は Z69 入院 / Z70 外来）
  - `a00` (0 歳) と `a01_04` (1-4 歳) は人口が 0-4 歳計しか無いため `population_thousand` = NaN
  - `a90p` (90 歳以上) は人口側が `a90_94 + a95_99 + a100p` に分かれるため NaN
  → 実用上、5-9 歳〜85-89 歳の 17 帯で人口結合が成立（Scale BB の標準グリッドと整合）

### 9.5 `mortality_apc_panel.parquet`

- **入力**: `5-15_死因_性_5歳階級_年次_死亡数率__0003411659.csv` ＋ 人口
- **行数**: 7,899
- **主キー**: (`disease_id`, `sex`, `age_code`, `year`)
- **年範囲**: 1950, 1955, 1960, 1965, 1970, 1975, 1980, 1985, 1990, 1995, 2000, 2005, 2010,
  2013-2024（25 時点）
- **収録 disease_id**: `total`, `cancer`, `heart_disease`, `cerebrovascular`, `hypertensive`
- **カラム**: `disease_id, mortality_code, disease_raw, sex, age_code, age_label, age_low,
  age_high, age_is_recap, age_is_total, year, deaths, rate_per_100k, population_thousand`
- **注**: Hi02/Hi04 は 2017 年 ICD-10 改定で `Hi022017` / `Hi042017` に内部コード変更。
  `MORTALITY_CODE_TO_FOCUS` が両系統を同一 ID に集約する。

### 9.6 実行方法

```powershell
$env:PYTHONIOENCODING = "utf-8"
python scripts/build_disease_panel.py
```

依存: `pandas`, `pyarrow`, `python-dotenv`（data 取得用）。標準で ~2 秒で完了。
