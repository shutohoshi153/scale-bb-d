**日本語** | [English](build_panel.en.md)

# 設計書 — `build_panel.py`（[1] 5-15 表 → 疾病パネル、§3.1）

> スクリプト横断の概要は [../SCRIPTS.md](../SCRIPTS.md)、パッケージ全体は [../README.md](../README.md) を参照。

## 1. 役割と位置づけ

人口動態統計 5-15 表（死因_性_5歳階級_年次_死亡数率、1950–2024）の生 CSV から、後段の全スクリプトが読む tidy 形式の疾病パネル `data/disease_panel_mortality.csv` を構築する。パイプラインの先頭（`run_all.sh` ステップ [1]）にあたり、論文 §3.1「データ・疾病マッピング」に対応する。

## 2. 入出力

**入力**

| ファイル | 内容 |
|---|---|
| `_paths.RAW_VITAL_CSV` | e-Stat 統計表 ID 0003411659 の生 CSV。列: `表章項目`（死亡数/死亡率）、`性別`、`年齢(5歳階級)`、`時間軸(年次)`、`死因年次推移分類_code`、`value` ほか |

※ `_paths.DISEASE_MAPPING`（`disease_estat_mapping.csv`）はパスとして参照されるが、実際の写像はスクリプト内の `DISEASE_TO_HICODE` 辞書にハードコードされている。CSV は §3.1.2 の対応表ドキュメントとしての位置づけ。

**出力**

| ファイル | 内容 |
|---|---|
| `data/disease_panel_mortality.csv` | パネル本体。列: `disease_id`, `sex`, `year`, `age_low`, `rate_per_100k`, `deaths`。8 疾病 × 3 性別 × 75 年 × 21 年齢階級 = 12,600 行規模 |
| `data/panel_summary.csv` | 検算用。疾病×性別ごとの行数・年数・年齢階級数・年範囲 |

出力が同梱の照合用 `data/prebuilt_disease_panel_mortality.csv` と一致することが、再現の第一チェックポイント。

## 3. CLI 引数

なし（`python build_panel.py` で実行）。

## 4. 処理フロー（`main()`）

1. **読込・前処理** — 生 CSV を読み、列名の BOM（U+FEFF）を除去。行数と年範囲をログ出力する。
2. **表章項目で分割** — `表章項目 == "死亡数"` の行（deaths）と `== "死亡率"` の行（rate。人口 10 万対）に分ける。
3. **列の正規化**（rate / deaths それぞれに適用）
   - `性別` → `sex`: {総数→total, 男→male, 女→female}
   - `年齢(5歳階級)` → `age_low`: `AGE_LABEL_TO_LOW` 辞書でラベルから下限年齢（0, 5, …, 100）へ。「総数」「不詳」は `None` に写して後段の `dropna` で除外。エンコーディング差異に強いよう、コードではなく**ラベル文字列**をキーにする。
   - `時間軸(年次)` → `year`: 「年」を除去して整数化。
4. **疾病写像** — `死因年次推移分類_code`（Hi コード）を `DISEASE_TO_HICODE` の逆引きで `disease_id` へ写像。対応のない死因・sex・年齢の行は `dropna` で落とす。
5. **結合・出力** — rate 側（`rate_per_100k`）に deaths 側（`deaths`）を `(disease_id, sex, year, age_low)` キーで左結合し、キー順にソートして CSV 出力。疾病×性別の要約表も併せて出力する。

## 5. 定数仕様

**`DISEASE_TO_HICODE`** — 疾病スラグ → 死因年次推移分類コード:

| disease_id | Hi コード | 備考 |
|---|---|---|
| cancer | `Hi022017` | 2017 年の分類改定により、1950–2024 全期間が 2017 年版コード側に格納 |
| diabetes | `Hi03` | |
| hypertensive | `Hi042017` | cancer と同様に 2017 年版コード |
| heart_disease | `Hi05` | 心疾患（高血圧性を除く）。論文・両再現パッケージ共通のスラグ |
| cerebrovascular | `Hi06` | |
| liver | `Hi11` | |
| kidney | `Hi12` | 腎不全（5-15 表上の最も近い区分） |
| total | `Hi00` | 全死因 |

虚血性心疾患（heart_ischemic）は死因年次推移分類に存在しない（死因簡単分類 5-28 のみで、5 歳階級がない）ため対象外。

**`AGE_LABEL_TO_LOW`** — 5 歳階級ラベル → 下限年齢の辞書（「0～4歳」→0 … 「100歳以上」→100。「総数」「不詳」→ `None`）。

## 6. 実装上の注意

- 死亡率は 5-15 表の値（人口 10 万対）を**そのまま**使用しており、本スクリプトでは率の再計算・補正は行わない。
- deaths の結合は `how="left"`（rate 側が主）。deaths が欠ける行があっても rate は保持される。
- 出力行の一意性は e-Stat 側のデータ品質に依存する（ピボットはせず、フィルタと結合のみで構成）。
