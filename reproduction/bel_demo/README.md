**日本語** | [English](README.en.md)

# bel_demo — §8 BEL 感応度デモの再現パッケージ（シナリオ生成器 → プロジェクション → 感応度表）

論文 §8（経済価値ベース評価下の BEL 感応度デモ）と付録 A（生命保険リスク所要資本・MOCE の簡易計算）を、`reproduction/` 配下だけで再実行できる形にまとめたもの。隣の `generational/` が「Scale BB-D を前向きに回して率テーブルを作る」段を担うのに対し、本パッケージはその**率テーブルを評価モデルに流し、規制シナリオの感応度表にするまで**を担う。表 8.3・図 8.1・表 A.1 はここから生成される。

**実務者向けの位置づけ**: 本パッケージは、論文 §9.2 の論拠 1・2（生成器は評価モデルの上流に置くだけで、出力は既存実務が読む率テーブル形式であり、静的表×一律係数のストレス表作成工程を置き換える）を実行可能な形で示すもの。`data/processed/scn_claim_rates.csv` の列仕様（`SCN_CD, BNFT_Q, GNDR_CD, ISSUE_AGE, DUR, ASSM_RT`）は評価モデルの入力形式に合わせて用意しており、率テーブル・モデルポイント・割引率を差し替えれば自社の感応度が得られる。

**位置づけの明示（§8.4 と同じ）**: 給付キャッシュフローのみ・脱退は独立近似・8 モデルポイントの**デモ用簡易モデル**であり、本番の評価モデルではない。実務モデル（FMS Booster）での突合は `../../fms_booster/` を参照。

## 構成

```
bel_demo/
├── README.md / README.en.md
├── _paths.py                       自己完結パス層（backtest/ のコアとパネルを共用）
├── run_all.sh                      ⓪〜⑤ 一括実行 + 参照出力との突合
├── check_reference.py              受入テスト（reference_output_20260930/ と相対誤差 1e-9 で突合。--reference-dir で切替）
├── build_esr_discount_curve.py     ⓪ ESR 無リスク金利カーブ（JPY・2026年3月末、Smith-Wilson）
├── build_scenario_claim_rates.py   ① シナリオ生成器: Phase 1 フィット 1 回 → L 差し替えで 6 シナリオ
├── verify_pipeline_rates.py        ② V1a: 率レベルの独立再導出・全件突合
├── calc_bel_standalone.py          ③ プロジェクション（式 8.1–8.2）+ V2/V3 チェック
├── aggregate_bel_results.py        ④ 表 8.3 / 図 8.1
├── calc_esr_life_risk.py           ⑤ 付録 A（告示 56–64 条・81 条・29–30 条）
├── data/external/fsa_esr/          金融庁公表資料（イールド・カーブ作成ツール）+ 出典 README
├── data/processed/                 再生成物（git 追跡外）
├── output/                         再生成物（git 追跡外）
├── reference_output/               2026-08 時点（平滑化グリッド修正前）の参照結果。共著者共有版と同一。現行コードでは一致しない
├── reference_output_20260902/      2026-09-02 修正後（コア annual_grid・lam_col=20、投影起点は平滑化率）の参照結果。現行コードでは一致しない
├── reference_output_20260903/      2026-09-03 修正後（投影起点を観測率に変更: コア `ScaleBBConfig.base_level="observed"`、論文 §3.2.2 式 3.6 の記述どおり）の合格済み参照結果（論文 §8・付録 A の現行数値の元。BASE BEL 合計 333,233 円）。現行コードでは一致しない
└── reference_output_20260930/      2026-09-30 修正後（死因別死亡給付としての評価: 3 死因による死亡を生存者から 1 回だけ除く、ESR_M = 死亡率 +12.5%）の合格済み参照結果
```

## 実行

```bash
cd reproduction/bel_demo
bash run_all.sh            # 6 スクリプト → check_reference.py で reference_output_20260930/ と突合
```

必要環境は `../backtest/README.md` と同じ（Python 3.10+、numpy / pandas / matplotlib）に `openpyxl` を加える。実行時間は数十秒程度。

## 各段の入出力

| 段 | スクリプト | 入力 | 出力 |
|---|---|---|---|
| ⓪ | `build_esr_discount_curve.py` | イールド・カーブ作成ツール パラメータシート（JPY: LOT=30 年、UFR 3.8%、収束年限 60 年、観測 13 年限） | `data/processed/esr_jpy_spot_curve_20260331.csv` |
| ① | `build_scenario_claim_rates.py` | `../backtest/data/prebuilt_disease_panel_mortality.csv`、`_scalebb_core`（`../backtest/vendor/`） | `scn_claim_rates.csv`（6 シナリオ × 3 疾病 × 2 性別）、`scn_mortality_rates.csv`（全死因・BASE 固定）、検算用 `rate_surface_*.csv` |
| ② | `verify_pipeline_rates.py` | ①の出力 | `output/verify_pipeline_rates.csv`（不一致 0 件で合格） |
| ③ | `calc_bel_standalone.py` | ①⓪の出力 | `output/bel_by_mp_scenario.csv`、`verify_bel_checks.csv` |
| ④ | `aggregate_bel_results.py` | ③の出力 | `output/bel_sensitivity_table.csv`（= 表 8.3）、`bel_sensitivity_bar.png`（= 図 8.1） |
| ⑤ | `calc_esr_life_risk.py` | ①⓪の出力 | `output/esr_life_risk_by_mp.csv`、`esr_life_risk_summary.csv`（= 表 A.1） |

## 仕様（§8.4–8.5）

- シナリオ 6 本: BASE (L=1.0%) / UP50 (1.5%) / DN50 (0.5%) / ICS_T (0%) / ICS_C (ICS_T × 1.125) / ESR_M (BASE × 1.125)。Phase 1 フィットは疾病×性別ごとに 1 回、Phase 2 のみ差し替え再投影（表 8.2 の実装列）
- モデルポイント 8 点: 加入年齢 30/40/50/60 × 男女、発行 2026 年、三大疾病（がん・心・脳血管）一時金 100 万円、90 歳満了
- 共通仮定: 解約率 3%/年、死亡脱退は全死因投影率（BASE 固定）、割引は ESR 無リスク金利カーブ（スプレッド調整なし）
- 規制ストレス係数: 1 柱告示 第 56 条 死亡リスク +12.5%（ESR_M と ICS_C のレベル部分。3 死因とその他の死因の両方に適用）

## 自社データで回す場合

1. `_paths.py` の `PANEL_CSV` を自社の死因別（または発生率）パネルに差し替える。列仕様は `../backtest/README.md` の `disease_panel_mortality.csv` と同じ（`disease_id, sex, age_low, year, rate`、per 100k）。
2. `calc_bel_standalone.py` の `MODEL_POINTS` / `LAPSE_RATE` / `SUM_ASSURED` を自社の商品・仮定に合わせる。
3. 割引率は `_paths.py` の `XLSX` を評価基準日のツールに差し替える（金融庁が四半期ごとに公表）。
4. `bash run_all.sh --skip-check` で実行（参照出力との突合は論文設定専用のため省略）。

自社の評価モデルに直接流す場合は、①の `scn_claim_rates.csv` を評価モデルの率テーブル形式へ変換して読み込めば、③以降は不要（§9.2 論拠 1）。実務モデルでの突合手順の実例は `../../fms_booster/` を参照。

## 同梱していないもの・ライセンス

- 金融庁公表資料（`data/external/fsa_esr/`）は金融庁の著作物であり、本リポジトリのライセンス（MIT / CC BY 4.0）は及ばない。告示 PDF は同梱せず、出典 URL を `data/external/fsa_esr/README.md` に記載。
- FMS Booster 側の入力生成スクリプト（`build_fms_input_tables.py` 等）は上流の研究側パイプラインに依存するため未同梱。生成済み入力 DB と突合スクリプトは `../../fms_booster/` にある。
- 原本は作業リポジトリ `ICA/ScaleBB/Research/scripts/bel_demo/`。パスアンカー以外は無改変（`Paper_ICA2026_publish/package_bel_demo.sh` で同期）。

## 検証状態

- V1a（率レベル全件突合）: 合格（不一致 0）
- V2（単調性 UP50 < BASE < DN50 < ICS_T < ICS_C）: 全 MP で成立
- V3（合成整合）: ICS_C/ICS_T = 1.09–1.11、ESR_M/BASE = 1.09–1.11（規定倍率との差は脱退相互作用分）
- 割引カーブ: 観測 13 年限を完全再現、収束年限 60 年で瞬間フォワード = UFR ± 1bp
- 主要結果（合計 BEL の BASE 比）: UP50 −6.7% / DN50 +7.3% / ICS_T +15.3% / ICS_C +26.2% / ESR_M +9.9%

## 感度分析用の変種（2026-09-30 追加）

`BEL_DEMO_VARIANT=deathweight` を付けて `build_esr_discount_curve.py` → `build_scenario_claim_rates.py` → `calc_bel_standalone.py` → `aggregate_bel_results.py` を実行すると、Phase 1 の平滑化を死亡数重み付き（`fit_scale_bb(..., weight=deaths)`）に替えた結果が `data/processed_deathweight/`・`output_deathweight/` に出力される（論文 §10 第 6 項）。参照値は `reference_output_20260930_deathweight/`。環境変数を付けなければ従来どおり論文の主結果（等重み）が `output/` に出力され、`check_reference.py` の突合対象も変わらない。

## 2026-09-30 の変更: 死因別死亡給付としての評価

論文の適用範囲を死因別死亡給付に限定したのに合わせ、BEL の計算（論文 式 8.1）を改めた。

- 生存者の更新: `S(t+1) = S(t)·(1 − q_dis − q_other − q_lapse)`。`q_dis` は 3 死因（がん・心疾患・脳血管疾患）の死亡率、`q_other` はその他の死因の死亡率（全死因 BASE − 3 死因 BASE）。2026-09-03 版までは健康事象の発現で支払う給付として `1 − q_dis − q_death − q_lapse`（`q_death` = 全死因）としており、死亡給付として読むと 3 死因による死亡が二重に脱退に入っていた。
- 水準ストレス ESR_M: 罹患・障害リスク +20%（第 59・60 条）から死亡リスク +12.5%（第 56 条）に変更。ICS_C・ESR_M ではその他の死因にも同じ係数をかける。
- 付録 A（`calc_esr_life_risk.py`）: 死亡サブリスク = ESR_M の ΔBEL、長寿・罹患障害サブリスクは 0。
- 結果: BASE の BEL 合計 333,233 → 364,198 円（+9.3%）、ICS_T の感応度は 0.5〜1.0pp 増。旧計算の結果は `reference_output_20260903/` に残る。新旧を並べる計算は `final/review/scripts/death_benefit_reading_a6.py`。
- 実稼働モデル（FMS）での突合（論文 §9.2）は旧計算で行ったもので、新計算では再実行していない。率表（`scn_claim_rates.csv`）の形式は同じで、ESR_M の倍率だけが変わる。

## 2026-09-30 の変更（再審査 A-9）: 中央死亡率から 1 年死亡確率への換算

率表（`scn_claim_rates.csv`・`scn_mortality_rates.csv`）は人口あたりの中央死亡率 m（10 万で除した値）のままとし、BEL の計算（`calc_bel_standalone.to_probabilities`）で全死因について q = 1 − exp(−m)（各年齢の 1 年間で死亡の力が一定という近似）に換算し、3 死因とその他の死因に率の比で配分する。付録 A（`calc_esr_life_risk.py`）の MOCE ランオフも同じ換算を使う。以前の q ≈ m に比べ、BASE の BEL 合計は 364,198 → 361,104 円（−0.8%）、感応度の変化は高々 0.3pp。参照出力 `reference_output_20260930/` はこの換算後の値に更新した（換算前の値は Git 履歴にある）。率表を評価モデルに直接読ませる場合、モデル側が率を確率として扱うなら同じ換算を行うこと。
