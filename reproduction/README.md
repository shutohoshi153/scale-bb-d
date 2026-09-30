**日本語** | [English](README.en.md)

# reproduction — §3 再現パッケージ群（査読者・共著者向け）

論文 §3「データと手法」の検証パイプラインと、§8「付帯的確認（BEL 感応度デモ）」を、単体で再現検証できる形にまとめたディレクトリ。
**3 つの相補的なパッケージ**が、公開データ → フィット・検証 → シナリオ別率テーブル → プロジェクション・感応度表、という一本の経路をカバーし、これに §7.3 の世代仮説の検出力分析 `cohort_power/` が加わる。

```
reproduction/
├── README.md        ← 本ファイル（分担と整合性の説明）
├── backtest/        点予測精度 + 方向性的中率の検証   （§3.1 / §3.2 / §3.3 / §5 / §6）
├── generational/    APC世代別 予定率テーブル生成       （§3.4・付録。詳細は generational/README.md）
├── bel_demo/        シナリオ生成器 → 簡易プロジェクション → 感応度表（§8。詳細は bel_demo/README.md）
└── cohort_power/    パンデミックのコホート効果の推定器: 公開データへの適用と検出力分析（§3.4 式 3.9・§7.3 表 7.2。詳細は cohort_power/README.md）
```

## 3 パッケージの分担

| パッケージ | 再現対象 | 実行系 | 入力 | 主な出力 |
|---|---|---|---|---|
| **`backtest/`** | バックテスト：3 cutoff × ScaleBB × 3 ベースラインの点予測 MAPE（式 3.7–3.8）と方向性的中率 DA（式 3.9–3.10） | 単体スクリプト（`run_all.sh`） | 人口動態統計 5-15 表（同梱） | `output/` 配下の検証テーブル・図 |
| **`generational/`** | APC fit/project → 発行年別 1D 予定率テーブル（世代投影） | EAS CLI（`experience_rate`） | `mortality_apc_panel`（同梱） | `reference_output/` と突合する予定率表 |
| **`bel_demo/`** | シナリオ別率テーブル（6 シナリオ、Phase 2 差し替え）→ BEL プロジェクション（式 8.1–8.2）→ 表 8.1・§8.2 の所要資本 | 単体スクリプト（`run_all.sh`） | `backtest/` のパネルとコアを共用、金融庁イールドカーブツール（同梱） | `output/` の感応度表・図、`reference_output/` と突合 |
| **`cohort_power/`** | 推定器 (3.9) の 14 系列への適用と、データ条件別の検出力（表 7.2） | 単体スクリプト 2 本 | `backtest/` のパネル（なければ同梱の prebuilt） | `output/public_data_theta.csv`、`output/power_summary.csv` |

`backtest/` は「Scale BB が点予測に向くか」を検証し（結論：MAPE では最良ベースラインに数 pp 及ばないが方向は保持する）、
`generational/` は「その改善率フレームワークを前向きに回して実務配布形式の率テーブルを作る」段を担い、
`bel_demo/` は「率テーブルを評価モデルに流して規制シナリオの感応度表にする」段を担う。
スコープは重複しない。

## 両パッケージの整合性（検証済み・2026-07-22）

共有ディレクトリとして矛盾がないことを以下で確認済み。

1. **アルゴリズムコアが同一**：`backtest/vendor/experience_rate/_scalebb_core/` と
   `generational/EAS/src/experience_rate/_scalebb_core/` は**ビット一致**（現行 EAS とも一致）。
   両パッケージは同一の Scale BB / APC 実装（§3.2 式 3.1–3.6、§3.4 式 3.7–3.8）を使う。
2. **入力死亡率データが同一**：両者とも e-Stat 人口動態統計の死因別死亡率が起点。
   共有セル（cancer / cerebrovascular / heart / hypertensive / total）で**完全一致**（差 0）を確認。
3. **データの位置づけが共通**：本研究の本来の対象は医療保険の罹患率とその世代効果であり、死因別死亡率は公開データ上の代替である。
   特定疾病死亡保障に対しては対象そのもの（2026-09-30 再改訂。保険会社は `backtest/run_own_data.py` と `cohort_power/` を自社の罹患・追跡データに流用できる）（§3.1.3・generational README §1）。
4. **中核ハイパーパラメータが共通**：`long_term_rate=0.01`、`convergence_year=2035`、
   `lam_row=40`、`diff_order=2`。

### 設定・表記の差（矛盾ではなく用途差）

| 項目 | `backtest/` | `generational/` | 備考 |
|---|---|---|---|
| `lam_col`（暦年方向平滑化） | 20 | 60 | [2026-09-30 訂正: 40 と誤記していた。本文 §3.2.3・`run_backtest.py` の `SCALE_BB_CONFIG` のとおり 20。設定の正は `backtest/output/MANIFEST.json` の `settings`] backtest は暦年連続グリッド化（2026-09-02）に伴い 40 → 20。generational は age20 移行で若年ノイズ抑制のため 60。各々の用途で正当（§3.2.3 脚注参照） |
| 年齢範囲 | 20–89 | 20–85（age20 プリセット） | 設定依存の軽微差 |

> 疾病スラグは両パッケージとも `heart_disease`（Hi05・心疾患・高血圧性除く）で統一済み。

## 使い方

```bash
# バックテスト（数分で全成果物を再生成）
cd backtest && bash run_all.sh

# 世代別予定率テーブル（EAS CLI。詳細は generational/README.md §3–4）
cd generational/EAS && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && export PYTHONPATH=src
python -m experience_rate scalebb-apc-fit --source mortality --sex male \
  --disease cancer heart_disease cerebrovascular --use-preset --run-id male_repro
```

各パッケージの詳細・期待される主要数値・改変点は、それぞれの `backtest/README.md` /
`generational/README.md` を参照。

## データ出典

両パッケージが同梱する第三者提供データ（人口動態調査・患者調査 / e-Stat、全国がん登録 /
国立がん研究センター、標準生命表 / 日本アクチュアリー会）の出典表記と利用条件は
`../DATA_SOURCES.md` に集約する。
