-- =============================================================================
-- Experience Rate Analysis System - Schema (SQLite)
-- =============================================================================
-- 個人医療保険の経験率分析および人口ベース疾病発生率ベンチマーク向けの
-- 正規化された SQLite スキーマ。
-- =============================================================================

-- -----------------------------------------------------------------------------
-- parameters: グローバル設定 (単一行)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS parameters (
    id                           INTEGER PRIMARY KEY CHECK (id = 1),
    observation_year_end_month   INTEGER NOT NULL
                                 CHECK (observation_year_end_month BETWEEN 1 AND 12),
    fiscal_year_end_month        INTEGER NOT NULL DEFAULT 9
                                 CHECK (fiscal_year_end_month BETWEEN 1 AND 12)
);

-- -----------------------------------------------------------------------------
-- rider_def: 特約定義 (経験率分析の集計軸となる特約マスタ)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rider_def (
    rider_code           TEXT PRIMARY KEY,
    rider_name           TEXT NOT NULL,
    rider_category       TEXT,                    -- 'medical' / 'cancer' / 'dread_disease' など
    display_order        INTEGER NOT NULL DEFAULT 0,
    description          TEXT
);

-- -----------------------------------------------------------------------------
-- population_incidence: 人口ベースの疾病発生率 (incidence rate) テーブル
-- -----------------------------------------------------------------------------
-- scripts/build_incidence_panel.py により生成された
-- data/processed/incidence_panel.csv をロードする。
--
-- rate_type:
--   'registry'       : 全国がん登録の罹患率 (真の incidence, 最高品質)
--   'initial_visit'  : 患者調査 Z70/Z13 の外来初診受療率ベース近似
--   'discharge'      : 患者調査 Z10 / 平均在院日数で算出した新規入院率
--   'mortality'      : 人口動態統計の死亡率 (致死率でキャップされる近似)
--   'prevalence_adj' : 受療率 ÷ 平均罹病期間 による incidence 逆算
--
-- quality_flag: A(真罹患) / B(初診近似) / C(退院近似) / D(死亡近似)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS population_incidence (
    disease_id              TEXT,              -- 'cancer', 'heart_disease' など (未分類は NULL 可)
    disease_norm            TEXT NOT NULL,     -- 日本語疾病名 (PK の一部)
    icd10                   TEXT,              -- ICD-10 コード (主にがん登録由来)
    sex                     INTEGER NOT NULL CHECK (sex IN (0, 1, 2)),
                            -- 0=総数, 1=男, 2=女
    age_code                TEXT NOT NULL,     -- 'a05_09', 'a60_64', 'a90p' など
    age_low                 INTEGER,           -- 年齢区間下限 (含む)
    age_high                INTEGER,           -- 年齢区間上限 (含む, 開区間は NULL)
    year                    INTEGER NOT NULL,  -- 西暦
    section                 TEXT NOT NULL DEFAULT 'total',
                            -- 'total' / 'inpatient' / 'outpatient' / 'onset'
    rate_type               TEXT NOT NULL CHECK (rate_type IN
                            ('registry', 'initial_visit', 'discharge',
                             'mortality', 'prevalence_adj')),
    incidence_rate_annual   REAL,              -- 年率 (無次元 0-1)
    incidence_rate_per_100k REAL,              -- 人口10万対
    numerator_count         REAL,              -- 分子 (実数/推計件数)
    population_thousand     REAL,              -- 分母 (千人)
    source_table            TEXT,              -- 出典ファイル / statsDataId
    quality_flag            TEXT,              -- 'A' / 'B' / 'C' / 'D'
    method_note             TEXT,              -- 推計方法の備考
    PRIMARY KEY (disease_norm, sex, age_code, year, section, rate_type)
);

CREATE INDEX IF NOT EXISTS idx_population_incidence_disease_year
    ON population_incidence(disease_id, year);

CREATE INDEX IF NOT EXISTS idx_population_incidence_age
    ON population_incidence(age_low, age_high);

-- -----------------------------------------------------------------------------
-- rider_disease_map: 特約 (rider_code) と疾病 (disease_id) の対応
-- -----------------------------------------------------------------------------
-- 1 つの特約が複数の疾病にまたがる場合は weight を用いて按分する。
-- preferred_rate_type は「この特約の発生率としてどの rate_type を第一選択するか」。
-- -----------------------------------------------------------------------------
-- rider_def は表示用ルックアップとして疎結合に扱い FK は設定しない。
-- (rider_def は load-incidence 時に rider_disease_map.csv 由来の rider_code
--  で自動補完される)
CREATE TABLE IF NOT EXISTS rider_disease_map (
    rider_code            TEXT NOT NULL,
    disease_id            TEXT NOT NULL,
    weight                REAL NOT NULL DEFAULT 1.0,  -- 疾病粒度の按分係数
    preferred_rate_type   TEXT,                        -- 第一選択 rate_type
    note                  TEXT,
    PRIMARY KEY (rider_code, disease_id)
);

-- -----------------------------------------------------------------------------
-- scalebb_run: Scale BB 拡張モデルの実行履歴 (fit / project のメタ情報)
-- -----------------------------------------------------------------------------
-- scripts/scale_bb_disease.py fit / project 実行ごとに 1 行が追加される。
-- config_json には ScaleBBConfig (lam_row, lam_col, long_term_rate,
-- convergence_year, horizon, age_taper_start/end 等) がそのまま JSON 保存される。
--
-- kind:
--   'fit'          : Phase 1 平滑化のみ (rate_observed + rate_smoothed + improvement_*)
--   'projection'   : Phase 2 投影 (長期率ブレンド + rate_projected)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scalebb_run (
    run_id              TEXT PRIMARY KEY,
    kind                TEXT NOT NULL CHECK (kind IN ('fit', 'projection')),
    source_panel        TEXT,              -- 'mortality_apc' / 'age_period' など
    diseases            TEXT,              -- 対象 disease_id のカンマ区切り
    sex                 TEXT,              -- 'total' / 'male' / 'female'
    section             TEXT,              -- 'total' / 'inpatient' / 'outpatient'
    age_min             INTEGER,
    age_max             INTEGER,
    year_min            INTEGER,
    year_max            INTEGER,
    long_term_rate      REAL,
    convergence_year    INTEGER,
    horizon_year        INTEGER,
    lam_row             REAL,
    lam_col             REAL,
    config_json         TEXT,              -- ScaleBBConfig 完全シリアライズ
    source_file         TEXT,              -- ロード元 CSV/parquet
    note                TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- -----------------------------------------------------------------------------
-- scalebb_improvement: Phase 1 fit 結果 (観測期間の平滑化改善率)
-- -----------------------------------------------------------------------------
-- 1 行 = (run_id, disease_id, sex, section, age, year) 組み合わせ。
-- rate_observed        : 入力観測率 (per 100,000)
-- rate_smoothed        : Whittaker-Henderson 2D 平滑化後率
-- improvement_observed : 観測率から算出した年率改善率 (t-1→t 幾何平均)
-- improvement_smoothed : 平滑化率から算出した年率改善率
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scalebb_improvement (
    run_id               TEXT NOT NULL,
    source_stream        TEXT,              -- 'mortality_apc/cancer' など
    disease_id           TEXT NOT NULL,
    sex                  TEXT NOT NULL,
    section              TEXT NOT NULL DEFAULT 'total',
    age                  INTEGER NOT NULL,
    year                 INTEGER NOT NULL,
    rate_observed        REAL,
    rate_smoothed        REAL,
    improvement_observed REAL,
    improvement_smoothed REAL,
    PRIMARY KEY (run_id, disease_id, sex, section, age, year),
    FOREIGN KEY (run_id) REFERENCES scalebb_run(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_scalebb_improvement_disease_year
    ON scalebb_improvement(disease_id, year);

-- -----------------------------------------------------------------------------
-- scalebb_projection: Phase 2 投影結果 (実績 + 将来の合成系列)
-- -----------------------------------------------------------------------------
-- 1 行 = (run_id, disease_id, sex, section, age, year) 組み合わせ (year は horizon まで)
-- is_observed          : 1=観測年, 0=将来投影年
-- improvement_final    : 原論文 h(y) 式で長期率 L へ線形収束させた改善率
-- rate_projected       : base_year から improvement_final で累積生成した投影率
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scalebb_projection (
    run_id               TEXT NOT NULL,
    source_stream        TEXT,
    disease_id           TEXT NOT NULL,
    sex                  TEXT NOT NULL,
    section              TEXT NOT NULL DEFAULT 'total',
    age                  INTEGER NOT NULL,
    year                 INTEGER NOT NULL,
    is_observed          INTEGER NOT NULL DEFAULT 0,
    improvement_final    REAL,
    rate_projected       REAL,
    PRIMARY KEY (run_id, disease_id, sex, section, age, year),
    FOREIGN KEY (run_id) REFERENCES scalebb_run(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_scalebb_projection_disease_year
    ON scalebb_projection(disease_id, year);

CREATE INDEX IF NOT EXISTS idx_scalebb_projection_observed
    ON scalebb_projection(is_observed, disease_id);

-- -----------------------------------------------------------------------------
-- scalebb_cohort_effect: APC 拡張のコホート効果 γ(c) 副テーブル
-- -----------------------------------------------------------------------------
-- scripts/scale_bb_apc_model.py の fit_scale_bb_apc が算出した γ(cohort) を
-- 格納する。cohort = year - age (出生年相当)。1 行 = (run_id, disease_id, sex,
-- section, cohort) の組み合わせ。
--
-- 二階差分罰則のため、γ(c) の絶対水準は未識別 (定数 + 線形の不定性) だが、
-- コホート間の相対差 (たとえば 1950 世代 vs 1970 世代) は解釈可能。
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scalebb_cohort_effect (
    run_id               TEXT NOT NULL,
    disease_id           TEXT NOT NULL,
    sex                  TEXT NOT NULL,
    section              TEXT NOT NULL DEFAULT 'total',
    cohort               INTEGER NOT NULL,   -- 出生年 (year - age)
    gamma                REAL,               -- γ(cohort) 対数スケール効果
    is_observed          INTEGER NOT NULL DEFAULT 1,  -- 1=fit 内で観測、0=外挿
    PRIMARY KEY (run_id, disease_id, sex, section, cohort),
    FOREIGN KEY (run_id) REFERENCES scalebb_run(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_scalebb_cohort_disease
    ON scalebb_cohort_effect (disease_id, sex, cohort);

-- -----------------------------------------------------------------------------
-- predicted_rate_generational: 発行年別 1D 予定発生率テーブル (下流配布用)
-- -----------------------------------------------------------------------------
-- scalebb_projection (3D: sex × age × year) を Generational Projection で
-- 切り出して、下流システム互換の [sex, age] ルックアップ形式にしたもの。
--
-- 数式: rate_per_100k[issue_year, sex, age]
--       = scalebb_projection.rate_projected[sex, age, year = issue_year + (age - issue_age)]
--
-- これにより下流 (契約管理・責任準備金計算) は既存の [sex, age] ルックアップ
-- API のまま、本研究モデルの恩恵を受けられる (issue_year は契約属性から選択)。
--
-- 参照例 (下流 SQL):
--   SELECT rate_per_100k FROM predicted_rate_generational
--   WHERE disease_id = :disease AND sex = :policy_sex
--     AND issue_year = :policy_issue_year AND age = :policy_current_age;
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS predicted_rate_generational (
    run_id               TEXT NOT NULL,
    disease_id           TEXT NOT NULL,
    sex                  TEXT NOT NULL,      -- 'total' / 'male' / 'female'
    section              TEXT NOT NULL DEFAULT 'total',
    issue_year           INTEGER NOT NULL,   -- 契約発行年 (テーブルバージョン軸)
    issue_age            INTEGER NOT NULL,   -- 契約時年齢 (通常 0 or 商品別)
    age                  INTEGER NOT NULL,   -- 参照年齢 (issue_age 以上)
    rate_per_100k        REAL,
    year_lookup          INTEGER,             -- 対応する暦年 = issue_year + (age - issue_age)
    PRIMARY KEY (run_id, disease_id, sex, section, issue_year, issue_age, age),
    FOREIGN KEY (run_id) REFERENCES scalebb_run(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pred_rate_gen_lookup
    ON predicted_rate_generational (disease_id, sex, issue_year, age);

CREATE INDEX IF NOT EXISTS idx_pred_rate_gen_run
    ON predicted_rate_generational (run_id);
