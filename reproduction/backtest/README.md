**日本語** | [English](README.en.md)

# backtest — §3 バックテスト再現パッケージ

本ディレクトリは、論文 §3「データと手法」の**バックテスト**（点予測精度と方向性的中率）を、**単体で再現検証**できるようにした自己完結パッケージである。生の人口動態統計 5-15 表から、点予測精度（§5）・方向性的中率（§6）の全成果物までを一括再生成する。

リポジトリの他ディレクトリには一切依存しない（入力データ・アルゴリズムコアをすべて同梱）。

各スクリプトの処理内容（入力・処理・出力）の詳細な解説は [SCRIPTS.md](SCRIPTS.md) を参照。

> `Paper_ICA2026/reproduction/` の 2 パッケージの一方。姉妹パッケージ `../generational/`
> （APC世代別予定率生成、§3.4・付録。詳細は `../generational/README.md`）とアルゴリズムコア・入力死亡率データを共有する。
> 分担と整合性の全体像は `../README.md` を参照。

---

## クイックスタート

```bash
# リポジトリ .venv を使う場合 (推奨。pandas/numpy/scipy/matplotlib 同梱)
bash run_all.sh

# Python を明示指定する場合
PY=/path/to/python bash run_all.sh
```

数分で完了し、全成果物が `./output/` 配下に生成される。

**依存:** Python 3.10+、`pandas` / `numpy` / `scipy` / `matplotlib` のみ。

---

## 自社の発生率実績で検証する（2026-09-30 追加）

論文は公開統計に発生率の長期パネルがないため死因別死亡率で検証している（論文 §7.3）。発生率の実績を持つ保険会社は、`run_own_data.py` で同じ検証（fit・投影・3 ベースライン・MAPE・方向性的中率と事後多数派ベンチマーク）を自社のパネルに対して実行できる。データは端末の外に出ない。

```bash
python run_own_data.py --panel /path/to/panel.csv --train-cutoff 2019 --validation-end 2024 --name own_2019
```

入力 CSV の列は `data/disease_panel_mortality.csv` と同じ:

| 列 | 内容 |
|---|---|
| `disease_id` | 任意のラベル（疾病・給付・特約） |
| `sex` | `total` / `male` / `female`（無い系列は飛ばす） |
| `year` | 観測年（欠測年があってよい） |
| `age_low` | 5 歳階級の下端年齢。20〜89 歳を使用 |
| `rate_per_100k` | 投影する率（エクスポージャー 10 万あたりの発生率・支払率） |
| `deaths` | 率の背後の件数（任意。等重みの fit では使わない） |

出力は `output/<name>/tables/`（`own_data_summary.csv` に系列別の MAPE と DA）。読み方: `DA_scalebb` を `DA_majority_benchmark`（論文 §3.3）と、`MAPE_scalebb` を 3 ベースライン（論文 §5）と比べる。構造変化の前後に cutoff を置くと情報が多い（論文 §4）。**率が 0 のセルの既定処理**（発生率では件数が少なく 0 が多い）: cutoff 年の率が 0 または欠測の年齢は、投影を平滑化率から始める（`select_base_rates` の既定）。その年齢は方向性的中率 DA の評価から除く（0 から測った方向は投影の方向を表さないため。論文 §3.3）。MAPE は実績率が 0 のセルを除く。0 が多い系列では、年齢階級を広げるか件数の多い系列に集約してから使うこと。

シナリオ生成と BEL 評価を自社データで回す手順は `../bel_demo/README.md` の「自社データで回す場合」を参照。

---

## パッケージ構成

```
backtest/
├── run_all.sh                       ワンショット再現ドライバ (§3 全パイプライン)
├── _paths.py                        自己完結パス層 (下記「元スクリプトからの改変」参照)
├── build_panel.py                   [1] 5-15 表 → 疾病パネル (§3.1)
├── run_backtest.py                  [2] ScaleBB fit/project + 検証 (§3.2)
├── run_baselines.py                 [3] naive/mean_3pts/loglin ベースライン (§3.3.1)
├── compute_directional_accuracy.py  [4] 方向性的中率 DA (§3.3.2, 式 3.9–3.10)。参照規則 always_down / sign_last_change、多数派方向比率、PT 検定、ブロック・ブートストラップ区間を含む [ADD 2026-09-02]
├── compute_da_inference.py          [4] DA の二方向（年齢 × 検証年）ブートストラップ区間、多数派ベンチマーク・loglin_trend との差 (§3.3, 表 6.1) [ADD 2026-09-30]
├── compute_rolling_origin.py        [4b] rolling-origin 2014–2022 の DA と MAPE 差 (§6.6, 図 6.4) [ADD 2026-09-02]。参照規則 majority_direction（窓ごとの多数派方向）、予測方向別の的中率、72 比較の勝敗表を含む [ADD 2026-09-03]
├── run_own_data.py                  自社の率パネルで同じ検証を実行（論文 §7.3）[ADD 2026-09-30]
├── compare_same_anchor.py           [3] 同一起点水準（観測率 / 直近 3 点平均 / 各手法の当てはめ値）でのトレンド比較 (§5.3, 表 5.4) [ADD 2026-09-30]
├── compute_fixed_horizon.py         [3] 固定ホライズン (h = 1, 2, 3 年先) の rolling-origin 比較、cutoff 2014–2023 (§5.3, 表 5.5) [ADD 2026-09-30]
├── compare_base_levels.py           [5b] 投影起点の水準（観測率 / 直近 3 観測点平均 / 平滑化率）の感度表 (§5.4, 表 5.5) [ADD 2026-09-03]
├── compute_weighted_mape.py         [5c] 死亡数重み MAPE・40 歳以上 MAPE (§5.4, 表 5.4) [ADD 2026-09-03]
├── compare_cutoffs.py               [5] 3 cutoff 横断比較 (§4)
├── make_calibration_recovery_figure.py  [6] 方向反転疾病の再キャリブレーション実験 (§6.5, 図 6.3)
├── make_paper_figures.py            [7] 論文掲載図の生成・収集 (→ ../../sections/figures/)
├── vendor/
│   └── experience_rate/_scalebb_core/
│       ├── model.py                 Scale BB コア (§3.2, 式 3.1–3.6)。EAS から無改変で同梱。[CHG 2026-09-03] 投影起点 `ScaleBBConfig.base_level`（既定 "observed" = 観測率、論文式 3.6 の記述どおり。旧実装は平滑化率）と収束期間 `convergence_period` を追加
│       └── apc_model.py             APC 拡張 (§3.4, 式 3.7–3.8)。参照用に同梱。[CHG 2026-09-03] `dummy` モードの非 COVID トレンドを局所窓（`covid_trend_window`=15 年）で当てはめるよう修正（付録 B 表 B.1、§10.5） [ADD 2026-09-03] `project_scale_bb_apc(apply_cohort=True)` で γ(c) を投影に持ち越す形を追加（既定は無効。§10.5 のテストでは cutoff 2014 で AP より改善、2019–2022 では劣後）。[CHG 2026-09-03] `decompose_apc_additive` に γ の線形成分除去とコホート軸平滑化（`lam_gamma`）を追加 [FIX 2026-09-30] コホート罰則を実際の出生コホート方向に修正（`cohort_year_step`: 年齢 1 階級につき暦年を階級幅ぶん進める。5 歳階級 × 暦年 1 年刻みで (i+1, j+5)。旧実装は (i+1, j+1) で出生コホートを辿っていなかった。付録 B 式 B.2）。`model.py` は不変で、§5–§6・§8 の数値には影響しない
├── data/
│   ├── raw/5-15_…_0003411659.csv    入力: 人口動態統計 5-15 表 (1950–2024)
│   ├── disease_estat_mapping.csv    疾病 → 死因コード対応 (§3.1.2)
│   └── prebuilt_disease_panel_mortality.csv   build_panel の期待出力 (照合用)
└── output/                          [生成物] run_all.sh で再構築 (git 管理外)
```

## 実行順序と §3 との対応

`run_all.sh` は報告書の再現手順に従い、以下を順に実行する。

| 順 | スクリプト | 生成物 | §3 の対応 |
|---|---|---|---|
| 1 | `build_panel.py` | `data/disease_panel_mortality.csv`（8疾病×3性別×25年×21年齢＝12,600行） | §3.1 データ・疾病マッピング |
| 2 | `run_backtest.py`（cutoff 2014/2021/2022） | `output[/cutoff_*]/tables/validation_summary.csv` ほか | §3.2 ScaleBB fit/project、式 (3.1)–(3.6) |
| 3 | `run_baselines.py`（同 3 cutoff） | `output[/cutoff_*]/tables/validation_summary_baseline.csv` ほか | §3.3.1 ベースライン、§3.3.2 MAPE/bias（式 3.7–3.8） |
| 4 | `compare_cutoffs.py` | `output/cutoff_comparison/` | §4 検証設計（3 cutoff 横断） |
| 5 | `compute_directional_accuracy.py` | `output/directional/` | §3.3.2 方向性的中率 DA（式 3.9–3.10）→ §6 |
| 6 | `make_calibration_recovery_figure.py` | `output/directional/tables/calibration_recovery.csv`、図 6.3（コミット対象） | §6.5 方向反転疾病の再キャリブレーション実験（liver / hypertensive、L・P 再設定 × cutoff） |
| 7 | `make_paper_figures.py` | `../../sections/figures/`（コミット対象） | 本文 §3・§4 の説明図の生成と、§5・§6 が参照する成果図の収集 |

## 期待される主要数値（照合用グラウンドトゥルース）

再現が正しく走ったかは、以下の代表値で確認できる（`sex=total`）。すべて論文 §5・§6 の表と一致する。値は主結果の設定（投影起点 = cutoff 年の観測率 `base_level="observed"`、`lam_row=40`・`lam_col=20`、暦年連続グリッド）によるものである。

**2026-09-30 訂正**: この節には 2026-09-03 以前の設定（投影起点 = 平滑化率）の値（cancer 7.17、total 7.73、DA total 84.29 など）が残っており、論文の主結果と一致していなかった（審査指摘 A-0）。平滑化率起点の値は現在 `output/base_smoothed_cutoff_*/` に分離して出力され、論文では表 5.4 の「自身の平滑化率」行に対応する。

**Scale BB-D MAPE [%]**（論文 表 5.2。`output[/cutoff_*]/tables/validation_summary.csv`）

| disease | 2014 | 2021 | 2022 |
|---|---:|---:|---:|
| cancer | 10.38 | 3.96 | 2.83 |
| total | 7.52 | 5.11 | 1.40 |
| hypertensive | 39.06 | 12.20 | 11.12 |

**方向性的中率 DA [%]**（論文 表 6.1。`output/directional/tables/directional_summary_total.csv`, cutoff=2014）

| disease | scalebb | naive_last | loglin_trend | 多数派ベンチマーク |
|---|---:|---:|---:|---:|
| total | 81.43 | 0.00 | 94.29 | 95.71 |
| cerebrovascular | 91.79 | 0.00 | 91.04 | 91.79 |
| cancer | 69.57 | 0.00 | 93.48 | 94.93 |

`naive_last` の DA が全セルで 0.00 になるのは、構造上 $\Delta_{\text{pred}} \equiv 0$ となり方向情報を持たないためである（論文 §3.3）。

**論文の表との自動照合**（2026-09-30 追加）

```bash
python verify_paper_tables.py                                  # 英語版 final/sections_en_b1
python verify_paper_tables.py --sections ../../final/sections  # 日本語版
```

論文 §5・§6 の Markdown から表 5.1〜5.5・6.1〜6.5 の全 442 セルを読み取り、`output/` の CSV から再計算した値と、印字の最終桁の半単位以内で一致するかを確認する（不一致があれば終了コード 1）。`run_all.sh` の最後に実行される。

**実行の記録と参照テーブル**（2026-09-30 追加）

`output/` は Git 管理外である。`run_all.sh` の最後に `write_manifest.py` が `output/MANIFEST.json`（入力データとアルゴリズムコアの SHA-256、コードの git commit、平滑化・投影の設定、ライブラリのバージョン、実行時刻）を書き、論文の表の元になる要約 CSV 14 本を `reference_tables/`（Git 管理対象）に写す。パイプラインを回さずに数値を確認する場合は `reference_tables/` を見ればよい。出力ディレクトリは設定ごとに分かれており上書きされない: 主結果 `output/`・`output/cutoff_<y>/`、起点水準の感度 `output/base_mean_obs_cutoff_<y>/`・`output/base_smoothed_cutoff_<y>/`。

## 元スクリプトからの改変（透明性のための明記）

同梱スクリプト 5 本は、研究側 `ScaleBB/BackTest_2015_2024/scripts/` の**アルゴリズム・集計・作図ロジックを一切変更していない**。改変したのは各ファイル先頭の**パスアンカー数行のみ**である:

- 元は `ROOT = Path(__file__).resolve().parents[2]` でリポジトリルートを辿り、`EAS/src`・`ScaleBB_Research/data/raw`・`MedicalInsuranceProduct/` を参照していた。2026-07 のリポジトリ再編でこれらは無効化された。
- 本パッケージでは、入力データとアルゴリズムコアを同梱し、`_paths.py` 1 か所で解決する。各スクリプトの改変箇所には `# [REPRO]` マーカーを付した。

`vendor/experience_rate/_scalebb_core/` は EAS（`ValidationTools/EAS/src/experience_rate/_scalebb_core/`）からの**無改変コピー**であり、§3.2/§3.4 の数式に対応する実装そのものである。

## データ出典・ライセンス

- **人口動態統計 5-15 表**（統計表 ID 0003411659）: 出典 **厚生労働省「人口動態調査」（政府統計の総合窓口 e-Stat）**。政府標準利用規約（第2.0版）に基づき出典明示のうえ商用利用可。
- 同梱する第三者提供データの出典一覧・利用条件は `../../DATA_SOURCES.md` を参照。
- 本パッケージは公開データに基づく学術的検証であり、特定商品の収益性・資本要件を保証しない（論文 §10 参照）。
