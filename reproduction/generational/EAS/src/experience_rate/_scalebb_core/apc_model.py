"""Scale BB 拡張モデルの APC (Age-Period-Cohort) 対応拡張。

`scripts/scale_bb_model.py` の 2D Whittaker-Henderson 平滑化を、
**対角 (コホート) 方向の差分罰則** を追加して APC モデルに拡張する。

数理要旨
--------

- 元の Scale BB (AP モデル): log m(x, t) を 2D 平滑化後、``β(t)`` 相当の改善率を
  長期率 L にブレンドして投影。コホート効果 γ(c) は期間効果に吸収される。

- 本拡張 (APC モデル): 目的関数を以下に変更。
  cohort = t - x 方向の二階差分も罰則項として加えることで、
  「同一出生コホート内での加齢軌跡」が滑らかになるよう制約。

    J(Z) = Σ_{i,j} w_{ij} (log m_{ij} - Z_{ij})^2
         + λ_age    · || D_age^(d)  Z      ||_F^2   (年齢方向)
         + λ_period · || Z D_period^(d)^T  ||_F^2   (暦年方向)
         + λ_cohort · || D_cohort^(d) vec(Z) ||^2   (対角方向 ← 新規)

- COVID 期 (2020-2022 等) は以下のいずれかで扱える:
    * ``covid_mode="weight_down"``: COVID 年の観測重みを ``covid_weight`` に下げる
      (平滑化で長期トレンドから外れないよう抑制)
    * ``covid_mode="dummy"``: COVID 年を別途 period 効果の dummy として処理
      (post-fit で COVID 年の β(t) シフトのみ抽出)
    * ``covid_mode="none"``: 通常扱い

識別可能性
----------
Age + Period = Cohort の線形関係により、3 効果の絶対水準と線形成分は未識別。
本実装は二階差分罰則を採用するため、定数項と線形項は自動的に罰則から除外され、
加法分解 ``log m(x, t) = α(x) + β(t) + γ(c)`` は
差分 (二階) レベルでのみ一意に識別される (Holford 1983 の枠組みに準拠)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import comb
from typing import Iterable, Literal

import numpy as np
from scipy.sparse import csr_matrix, diags, eye, kron, lil_matrix
from scipy.sparse.linalg import spsolve

from dataclasses import replace

from .model import (
    expand_to_annual_grid,
    ScaleBBConfig,
    ScaleBBFitResult,
    _difference_matrix,
    build_blended_improvements,
    compute_annual_improvement,
    project_rates,
    select_base_rates,
)


# ---------------------------------------------------------------------------
# Cohort (diagonal) difference matrix
# ---------------------------------------------------------------------------
def cohort_year_step(ages: np.ndarray, years: np.ndarray) -> int:
    """年齢階級を 1 つ進めるときに、同一出生コホートが進む暦年インデックス数 s を返す。

    [FIX 2026-09-30] 出生コホート c = y − x を辿るには、年齢が 1 階級 (幅 w_x 年) 進むごとに
    暦年も w_x 年進めなければならない。年軸の刻みが w_y 年なら s = w_x / w_y
    (5 歳階級 × 暦年 1 年刻みで s = 5、各歳 × 1 年刻みで s = 1)。
    年齢・暦年が等間隔でない、または s が整数にならない格子ではコホート対角が
    格子点に乗らないため ValueError とする (暦年は ``annual_grid=True`` で連続化すること)。
    """
    ages = np.asarray(ages, dtype=float)
    years = np.asarray(years, dtype=float)
    if ages.size < 2 or years.size < 2:
        return 1
    age_gaps = np.diff(ages)
    year_gaps = np.diff(years)
    if not np.allclose(age_gaps, age_gaps[0]) or not np.allclose(year_gaps, year_gaps[0]):
        raise ValueError(
            "cohort penalty needs equally spaced ages and years "
            "(use annual_grid=True for irregular observation years)"
        )
    ratio = float(age_gaps[0]) / float(year_gaps[0])
    step = int(round(ratio))
    if step < 1 or abs(ratio - step) > 1e-9:
        raise ValueError(
            f"age width {age_gaps[0]} is not an integer multiple of year width {year_gaps[0]}; "
            "the cohort diagonal does not fall on grid points"
        )
    return step


def diagonal_difference_matrix(
    n_age: int,
    n_year: int,
    diff_order: int = 2,
    year_step: int = 1,
) -> csr_matrix:
    """対角 (cohort = year − age) 方向の ``diff_order`` 階差分行列。

    ``vec(Z)`` は Fortran order (column-major, 列方向=年次) を前提とし、
    ``vec(Z)[i + n_age * j] = Z[i, j]``。同一コホート内で年齢階級 i を 1 つ
    進めると暦年インデックスは ``year_step`` (= 年齢階級幅 / 暦年刻み、
    ``cohort_year_step`` 参照) だけ進み (i+1, j+s) となるため、対角方向の d 階差分は

        Σ_{k=0..d} (-1)^{d-k} C(d, k) · Z[i+k, j+s·k]

    として定義。罰則項は ``|| D vec(Z) ||^2`` の二次形式。

    [FIX 2026-09-30] 旧実装は s = 1 固定で、5 歳階級 × 暦年 1 年刻みの格子では
    (x+5, y+1) を結んでおり、出生コホート (y − x 一定) を辿っていなかった。

    Args:
        n_age:   年齢階級数
        n_year:  年数
        diff_order: 差分階数 (通常 2)
        year_step: 年齢 1 階級あたりの暦年インデックスの進み s

    Returns:
        shape = ((n_age - d) × (n_year - s·d), n_age * n_year) の疎行列。
    """
    d = diff_order
    s = int(year_step)
    if d < 1:
        raise ValueError("diff_order must be >= 1")
    if s < 1:
        raise ValueError("year_step must be >= 1")
    if n_age <= d or n_year <= s * d:
        # コホート方向のセルが足りない場合は空行列
        return csr_matrix((0, n_age * n_year))

    # 二項係数 (-1)^{d-k} * C(d, k)
    coefs = np.array([(-1) ** (d - k) * comb(d, k) for k in range(d + 1)], dtype=float)

    n_rows = (n_age - d) * (n_year - s * d)
    n_cols = n_age * n_year
    mat = lil_matrix((n_rows, n_cols))

    row_idx = 0
    for j in range(n_year - s * d):
        for i in range(n_age - d):
            for k in range(d + 1):
                col = (i + k) + n_age * (j + s * k)
                mat[row_idx, col] = coefs[k]
            row_idx += 1
    return mat.tocsr()


# ---------------------------------------------------------------------------
# APC 2D smoother
# ---------------------------------------------------------------------------
def whittaker_henderson_apc(
    y: np.ndarray,
    *,
    weight: np.ndarray | None = None,
    lam_age: float = 40.0,
    lam_period: float = 40.0,
    lam_cohort: float = 40.0,
    diff_order: int = 2,
    cohort_year_step: int = 1,
) -> np.ndarray:
    """対角罰則付き 2D Whittaker-Henderson 平滑化 (APC 版)。

    Args:
        y: shape (n_age, n_year) の観測値行列 (NaN は重み 0 扱い)
        weight: 同 shape の重み。None なら有限値セルに 1.0、NaN に 0.0
        lam_age: 年齢方向 (行方向) の平滑化パラメータ
        lam_period: 暦年方向 (列方向) の平滑化パラメータ
        lam_cohort: コホート方向 (対角方向) の平滑化パラメータ (新規)
        diff_order: 差分階数
        cohort_year_step: 年齢 1 階級あたりの暦年インデックスの進み
            (``cohort_year_step(ages, years)``。5 歳階級 × 暦年 1 年刻みなら 5)

    Returns:
        shape (n_age, n_year) の平滑化後行列。
    """
    y = np.asarray(y, dtype=float)
    if y.ndim != 2:
        raise ValueError("y must be 2-D")
    n_age, n_year = y.shape

    if weight is None:
        weight = np.ones_like(y)
    weight = np.asarray(weight, dtype=float).copy()
    nan_mask = ~np.isfinite(y)
    y = np.where(nan_mask, 0.0, y)
    weight[nan_mask] = 0.0
    weight = np.where(np.isfinite(weight) & (weight >= 0), weight, 0.0)

    # vec(Z) は F-order: vec(Z)[i + n_age * j] = Z[i, j]
    w_vec = weight.flatten(order="F")
    y_vec = y.flatten(order="F")

    d_age = _difference_matrix(n_age, diff_order)
    d_year = _difference_matrix(n_year, diff_order)
    d_cohort = diagonal_difference_matrix(
        n_age, n_year, diff_order=diff_order, year_step=cohort_year_step
    )

    p_age = kron(eye(n_year, format="csr"), (d_age.T @ d_age), format="csr")
    p_year = kron((d_year.T @ d_year), eye(n_age, format="csr"), format="csr")
    p_cohort = (d_cohort.T @ d_cohort).tocsr() if d_cohort.shape[0] > 0 else csr_matrix(
        (n_age * n_year, n_age * n_year)
    )

    w_diag = diags(w_vec, 0, format="csr")
    a = (
        w_diag
        + lam_age * p_age
        + lam_period * p_year
        + lam_cohort * p_cohort
    ).tocsc()
    b = w_vec * y_vec
    z_vec = spsolve(a, b)
    return z_vec.reshape((n_age, n_year), order="F")


# ---------------------------------------------------------------------------
# APC 加法分解: log m(x, t) = α(x) + β(t) + γ(c) + residual
# ---------------------------------------------------------------------------
def decompose_apc_additive(
    log_rate_smoothed: np.ndarray,
    ages: np.ndarray,
    years: np.ndarray,
    *,
    weight: np.ndarray | None = None,
    max_iter: int = 200,
    tol: float = 1e-8,
    gamma_smooth_lambda: float = 25.0,
) -> dict[str, np.ndarray]:
    """平滑化済み対数率を α(x) + β(t) + γ(c) に加法分解 (加重最小二乗反復法)。

    [CHG 2026-09-03] 2 点を修正 (論文 final/review の予備検討で判明した欠陥):
      (1) γ(c) の線形成分を毎反復で明示的に除去し、Holford 規約どおり b·c = b·t − b·x を
          β(t) と α(x) に移す (旧実装は規約をコメントで述べるだけで数値的には強制していなかった)。
      (2) γ(c) をコホート軸に沿って 1 次元 Whittaker-Henderson (2 階差分、λ = gamma_smooth_lambda、
          重み = コホート別セル数) で平滑化する。5 歳階級 × 年次グリッドではコホート c = t − x が
          年次で定義される一方、実体は 5 年帯であるため、隣接コホートの γ が交互に振れる。
          gamma_smooth_lambda=0 で旧挙動 (平滑化なし)。

    識別可能性のため、参照制約を設ける:
    - α(x_ref) = 0  (x_ref = 最小年齢)
    - β(t_ref) = 0  (t_ref = 最小暦年)
    - γ(c) は二階差分ゼロ + 最小コホートを基準
    
    線形成分は period と cohort に分配される ambiguity が残るが、
    本関数は「intercept を period に、drift を year に乗せる」Holford 規約に従う。

    Returns:
        {"alpha": (n_age,), "beta": (n_year,), "gamma": (n_cohort,),
         "cohorts": (n_cohort,), "residual": (n_age, n_year)}
    """
    log_rate_smoothed = np.asarray(log_rate_smoothed, dtype=float)
    ages = np.asarray(ages, dtype=int)
    years = np.asarray(years, dtype=int)
    n_age, n_year = log_rate_smoothed.shape
    if weight is None:
        weight = np.where(np.isfinite(log_rate_smoothed), 1.0, 0.0)
    else:
        weight = np.asarray(weight, dtype=float).copy()
    mask = weight > 0

    # cohort index
    cohort_matrix = years[np.newaxis, :] - ages[:, np.newaxis]
    cohorts_unique = np.unique(cohort_matrix)
    cohort_idx = {c: k for k, c in enumerate(cohorts_unique)}
    n_cohort = len(cohorts_unique)

    alpha = np.zeros(n_age)
    beta = np.zeros(n_year)
    gamma = np.zeros(n_cohort)

    y = np.where(mask, log_rate_smoothed, 0.0)

    prev_loss = np.inf
    for it in range(max_iter):
        # α(x) 更新 (β, γ 固定)
        for i in range(n_age):
            w_i = weight[i, :]
            if w_i.sum() == 0:
                continue
            g_i = np.array([gamma[cohort_idx[cohort_matrix[i, j]]] for j in range(n_year)])
            resid = y[i, :] - beta - g_i
            alpha[i] = np.sum(w_i * resid) / w_i.sum()
        # β(t) 更新
        for j in range(n_year):
            w_j = weight[:, j]
            if w_j.sum() == 0:
                continue
            g_j = np.array([gamma[cohort_idx[cohort_matrix[i, j]]] for i in range(n_age)])
            resid = y[:, j] - alpha - g_j
            beta[j] = np.sum(w_j * resid) / w_j.sum()
        # γ(c) 更新
        cohort_num = np.zeros(n_cohort)
        cohort_den = np.zeros(n_cohort)
        for i in range(n_age):
            for j in range(n_year):
                if not mask[i, j]:
                    continue
                k = cohort_idx[cohort_matrix[i, j]]
                r = y[i, j] - alpha[i] - beta[j]
                cohort_num[k] += weight[i, j] * r
                cohort_den[k] += weight[i, j]
        gamma = np.where(cohort_den > 0, cohort_num / np.where(cohort_den > 0, cohort_den, 1), 0.0)

        # [CHG 2026-09-03] (2) γ をコホート軸で平滑化 (重み = セル数)
        if gamma_smooth_lambda and gamma_smooth_lambda > 0 and n_cohort >= 3:
            Dg = np.diff(np.eye(n_cohort), n=2, axis=0)
            Wg = np.diag(cohort_den)
            gamma = np.linalg.solve(Wg + gamma_smooth_lambda * Dg.T @ Dg, Wg @ gamma)
        # [CHG 2026-09-03] (1) γ の線形成分 b0 + b1·c を除去し、b1·c = b1·t − b1·x を β・α へ移す
        cw = np.where(cohort_den > 0, cohort_den, 0.0)
        if cw.sum() > 0:
            cc = cohorts_unique.astype(float)
            b1, b0 = np.polyfit(cc, gamma, 1, w=np.sqrt(cw))
            gamma = gamma - (b0 + b1 * cc)
            beta = beta + b0 + b1 * years.astype(float)
            alpha = alpha - b1 * ages.astype(float)

        # 識別制約: α(x_ref) = 0, β(t_ref) = 0
        # (γ の定数・線形成分は未識別だが、数値的に安定化のため中心化)
        a_shift = alpha[0]
        alpha -= a_shift
        beta += a_shift  # intercept を β に吸収
        b_shift = beta[0]
        beta -= b_shift
        # β のドリフト (線形) は γ に押し付けない Holford 規約
        # γ の中心化: 平均 0 (加重) にはしない (cohort ドリフトを保持)

        # 収束判定: 重み付き RSS
        resid_mat = np.zeros_like(y)
        for i in range(n_age):
            for j in range(n_year):
                resid_mat[i, j] = y[i, j] - alpha[i] - beta[j] - gamma[cohort_idx[cohort_matrix[i, j]]]
        loss = float(np.sum(weight * resid_mat ** 2))
        if abs(prev_loss - loss) < tol:
            break
        prev_loss = loss

    return {
        "alpha": alpha,
        "beta": beta,
        "gamma": gamma,
        "cohorts": cohorts_unique,
        "residual": resid_mat,
    }


# ---------------------------------------------------------------------------
# COVID weight handling
# ---------------------------------------------------------------------------
def build_covid_weight(
    ages: np.ndarray,
    years: np.ndarray,
    *,
    base_weight: np.ndarray | None = None,
    covid_years: Iterable[int] = (2020, 2021, 2022),
    covid_weight: float = 0.3,
    mode: Literal["weight_down", "dummy", "none"] = "weight_down",
) -> np.ndarray:
    """COVID 期間の重み行列を生成。

    mode:
        - ``weight_down``: COVID 年の観測重みを ``covid_weight`` 倍
        - ``dummy`` / ``none``: base_weight をそのまま返す (dummy 処理は別層で)
    """
    n_age, n_year = len(ages), len(years)
    if base_weight is None:
        w = np.ones((n_age, n_year))
    else:
        w = np.asarray(base_weight, dtype=float).copy()
    if mode == "weight_down":
        covid_set = set(int(y) for y in covid_years)
        for j, y in enumerate(years):
            if int(y) in covid_set:
                w[:, j] = w[:, j] * covid_weight
    return w


# ---------------------------------------------------------------------------
# APC Config / FitResult
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ScaleBBAPCConfig(ScaleBBConfig):
    """APC 拡張の追加パラメータ付き設定。

    ScaleBBConfig の ``lam_row`` / ``lam_col`` はそれぞれ
    年齢方向 / 暦年方向の平滑化 λ として再利用する。
    ScaleBBConfig が frozen なので本クラスも frozen=True で継承。
    """

    lam_cohort: float = 40.0
    covid_years: tuple[int, ...] = (2020, 2021, 2022)
    covid_weight: float = 0.3
    covid_mode: Literal["weight_down", "dummy", "none"] = "weight_down"
    # [ADD 2026-09-03] dummy モードで β(t) の「非 COVID トレンド」を当てはめる局所窓 (年)。
    # 旧実装は 1950 年以降の全非 COVID 年に直線を当てはめており、数十年にわたる β の曲率を
    # COVID ショックとして誤抽出していた (論文 final/review の APC 予備検討で判明)。
    # 窓は [min(covid_years) − covid_trend_window, max(covid_years) + covid_trend_window] の非 COVID 年。
    covid_trend_window: int = 15
    # [ADD 2026-09-03] γ(c) のコホート軸平滑化強度 (decompose_apc_additive の gamma_smooth_lambda)。0 で無効。
    lam_gamma: float = 25.0


@dataclass
class ScaleBBAPCFitResult(ScaleBBFitResult):
    """APC 分解結果を保持する拡張クラス。"""

    alpha: np.ndarray | None = None      # α(age), shape (n_age,)
    beta: np.ndarray | None = None       # β(period), shape (n_year,)
    gamma: np.ndarray | None = None      # γ(cohort), shape (n_cohort,)
    cohorts: np.ndarray | None = None    # cohort ラベル (年)
    covid_adjustment: np.ndarray | None = None  # COVID 年の period shift (if dummy mode)


# ---------------------------------------------------------------------------
# High-level APC fit / project API
# ---------------------------------------------------------------------------
def fit_scale_bb_apc(
    rate_matrix: np.ndarray,
    ages: Iterable[int | float],
    years: Iterable[int],
    *,
    config: ScaleBBAPCConfig | None = None,
) -> ScaleBBAPCFitResult:
    """APC 拡張版 Scale BB Phase 1 フィット。

    - log スケールで APC 平滑化 (対角罰則込み)
    - COVID 年は重みダウン or dummy で扱う
    - 加法分解 α/β/γ を算出
    - 改善率は「(observed, smoothed) それぞれから年次差分」で従来 Scale BB と同形式

    Returns:
        ScaleBBAPCFitResult (ScaleBBFitResult を拡張)
    """
    cfg = config or ScaleBBAPCConfig()
    ages_arr = np.asarray(list(ages), dtype=float)
    years_arr = np.asarray(list(years), dtype=int)
    rates = np.asarray(rate_matrix, dtype=float)

    if rates.shape != (ages_arr.size, years_arr.size):
        raise ValueError(
            f"rate_matrix shape {rates.shape} != ({ages_arr.size}, {years_arr.size})"
        )
    if np.any(np.diff(years_arr) <= 0):
        raise ValueError("years must be strictly increasing")

    with np.errstate(divide="ignore", invalid="ignore"):
        log_r = np.where(rates > 0, np.log(rates), np.nan)
    base_weight = np.where(np.isfinite(log_r), 1.0, 0.0)
    weight = build_covid_weight(
        ages_arr,
        years_arr,
        base_weight=base_weight,
        covid_years=cfg.covid_years,
        covid_weight=cfg.covid_weight,
        mode=cfg.covid_mode,
    )

    if cfg.annual_grid:
        # [FIX 2026-09-02] 暦年連続グリッド上で平滑化 (model.fit_scale_bb と同じ扱い)。
        # [FIX 2026-09-30] コホート対角 c = y - x は、年齢 1 階級につき暦年を階級幅ぶん
        # (5 歳階級なら 5 年) 進める方向。cohort_year_step がその格子ステップを与える。
        log_r_full, weight_full, _full_years, obs_idx = expand_to_annual_grid(
            log_r, years_arr, weight=weight
        )
        log_r_smoothed = whittaker_henderson_apc(
            log_r_full,
            weight=weight_full,
            lam_age=cfg.lam_row,
            lam_period=cfg.lam_col,
            lam_cohort=cfg.lam_cohort,
            diff_order=cfg.diff_order,
            cohort_year_step=cohort_year_step(ages_arr, _full_years),
        )[:, obs_idx]
    else:
        log_r_smoothed = whittaker_henderson_apc(
            log_r,
            weight=weight,
            lam_age=cfg.lam_row,
            lam_period=cfg.lam_col,
            lam_cohort=cfg.lam_cohort,
            diff_order=cfg.diff_order,
            cohort_year_step=cohort_year_step(ages_arr, years_arr),
        )
    rate_smoothed = np.exp(log_r_smoothed)

    imp_obs = compute_annual_improvement(rates, years_arr)
    imp_smoothed = compute_annual_improvement(rate_smoothed, years_arr)

    # 加法分解 (平滑化 log 率 → α + β + γ + residual)
    decomp = decompose_apc_additive(
        log_r_smoothed,
        ages=ages_arr.astype(int),
        years=years_arr,
        weight=weight,
        gamma_smooth_lambda=cfg.lam_gamma,
    )

    # COVID dummy モード: COVID 年の β を非 COVID 線形補間値に置換して shift 抽出。
    # 重要: α + β + γ の加法分解は識別制約 (α[0]=0, β[0]=0) により定数・線形
    # 成分を捨てるため、そのまま log_rate = α + β + γ で再構築すると絶対水準を
    # 失う (例: log_rate=5 → 0.5 のような大幅な変換)。
    # そこで **元の log_r_smoothed から COVID 期の β ショックのみを差し引く**
    # 形で補正し、絶対水準を保持する。
    covid_adj = None
    if cfg.covid_mode == "dummy":
        beta = decomp["beta"].copy()
        mask_covid = np.array(
            [int(y) in set(cfg.covid_years) for y in years_arr], dtype=bool
        )
        idx_all = np.arange(len(years_arr))
        # [CHG 2026-09-03] 局所窓内の非 COVID 年のみで直線を当てはめる
        lo = min(cfg.covid_years) - int(cfg.covid_trend_window)
        hi = max(cfg.covid_years) + int(cfg.covid_trend_window)
        in_win = (years_arr >= lo) & (years_arr <= hi)
        idx_non = idx_all[~mask_covid & in_win]
        if idx_non.size < 2:
            idx_non = idx_all[~mask_covid]
        if idx_non.size >= 2:
            poly = np.polyfit(years_arr[idx_non], beta[idx_non], deg=1)
            beta_trend = np.polyval(poly, years_arr)
            covid_adj = np.where(mask_covid, beta - beta_trend, 0.0)
            beta_corrected = np.where(mask_covid, beta_trend, beta)
            decomp["beta"] = beta_corrected

            # COVID ショック (β - β_trend) のみを log 空間で差し引く
            # → 絶対水準・年齢別構造・コホート効果はそのまま保持
            beta_shock = covid_adj  # shape (n_year,)
            log_rate_corrected = log_r_smoothed - beta_shock[np.newaxis, :]
            rate_smoothed = np.exp(log_rate_corrected)
            imp_smoothed = compute_annual_improvement(rate_smoothed, years_arr)

    return ScaleBBAPCFitResult(
        ages=ages_arr,
        years=years_arr,
        rate_observed=rates,
        rate_smoothed=rate_smoothed,
        improvement_observed=imp_obs,
        improvement_smoothed=imp_smoothed,
        config=cfg,
        alpha=decomp["alpha"],
        beta=decomp["beta"],
        gamma=decomp["gamma"],
        cohorts=decomp["cohorts"],
        covid_adjustment=covid_adj,
    )


def project_scale_bb_apc(
    fit: ScaleBBAPCFitResult,
    *,
    base_year: int | None = None,
    cohort_extrapolation: Literal["flat", "last_drift"] = "last_drift",
    apply_cohort: bool = False,
) -> ScaleBBAPCFitResult:
    """APC フィット結果を将来年へ投影。

    投影戦略:
    1. 改善率 i(x, t) を従来 Scale BB と同様に長期率 L へ線形収束
    2. 投影年度に対応するコホート (= 投影年 − age) のうち、
       訓練期間で観測済みのコホートは γ(c) を適用、
       未観測コホート (= 直近で新生するコホート) は ``cohort_extrapolation`` に従い:
         - "flat"        : γ(c) = 最後に観測された γ
         - "last_drift"  : γ(c) 末尾の一階差分を外挿 (線形延長)
    3. 投影率 = α + β(投影) + γ(c) で log 空間加算 → exp で率空間に戻す
       ただし base_year は観測粗率からの累積投影 (改善率パスに沿う) に統一

    注意: 本関数は AP 的な改善率投影 (既存 Scale BB) と整合させるため、
    rate_projected = project_rates(base_rates=rate_smoothed@base_year, improvement=i*)
    を採用する。α/β/γ 分解は解釈・レポート用として保持する。
    """
    cfg: ScaleBBAPCConfig = fit.config  # type: ignore[assignment]
    last_obs = (
        int(cfg.last_observed_year)
        if cfg.last_observed_year is not None
        else int(fit.years.max())
    )
    # [CHG 2026-09-03] ブレンド設定は cfg をそのまま使う (convergence_period 等を継承)。
    improvement_final, projection_years = build_blended_improvements(
        fit.improvement_smoothed,
        years=fit.years,
        ages=fit.ages,
        config=replace(cfg, last_observed_year=last_obs),
    )

    base = base_year if base_year is not None else last_obs
    # [CHG 2026-09-03] 投影起点は model.select_base_rates に統一 (既定 = 観測率、論文 §3.2.2 式 3.6)。
    base_rates = select_base_rates(fit, base, cfg.base_level, cfg.base_obs_points)
    rate_projected = project_rates(
        base_rates, improvements=improvement_final, base_year=base, years=projection_years
    )

    # コホート外挿 (γ(c) 未観測部分)
    ages_int = fit.ages.astype(int)
    if fit.gamma is not None and fit.cohorts is not None:
        gamma_ext, cohorts_ext = _extrapolate_gamma(
            fit.gamma, fit.cohorts, ages_int, projection_years, mode=cohort_extrapolation
        )
        fit.gamma, fit.cohorts = gamma_ext, cohorts_ext

        # [ADD 2026-09-03] apply_cohort=True: γ(c) を投影に持ち越す (付録 B の設計)。
        #   log m_APC(x, y) = log m(x, base) + Σ_{u=base+1..y} log(1 − i*_β(x, u)) + [γ(y − x) − γ(base − x)]
        # ここで i*_β は **期間効果 β(y) のみ** から得た改善率 1 − exp(β(y) − β(y−1)) を L へブレンドしたもの。
        # AP 型の改善率 i(x, y) = −Δβ(y) − Δγ(y − x) はコホート勾配を既に含むため、それに γ を重ねると
        # 二重計上になる。よって cohort 持ち越し時は改善率を β 成分に置き換える。
        # γ ≡ 0 かつ β 成分 = AP 改善率のとき AP 投影と一致する。γ は Holford 規約で線形成分を β 側に
        # 置いて識別されているので、乗じるのは二階差分で識別される非線形部分のみ。
        if apply_cohort and fit.beta is not None:
            beta = np.asarray(fit.beta, dtype=float)
            n_age, n_year = fit.rate_smoothed.shape
            year_gaps = np.diff(fit.years.astype(float))
            i_beta = np.full(n_year, np.nan)
            i_beta[1:] = 1.0 - np.exp(np.diff(beta) / year_gaps)
            imp_beta = np.tile(i_beta, (n_age, 1))
            improvement_final, projection_years = build_blended_improvements(
                imp_beta, years=fit.years, ages=fit.ages, config=replace(cfg, last_observed_year=last_obs)
            )
            rate_projected = project_rates(
                base_rates, improvements=improvement_final, base_year=base, years=projection_years
            )
            gmap = {int(c): float(g) for c, g in zip(cohorts_ext, gamma_ext)}
            base_idx = int(np.where(projection_years == base)[0][0])
            for k in range(base_idx + 1, len(projection_years)):
                y = int(projection_years[k])
                for i, a in enumerate(ages_int):
                    adj = gmap.get(y - int(a), 0.0) - gmap.get(base - int(a), 0.0)
                    rate_projected[i, k] *= float(np.exp(adj))

    fit.projection_years = projection_years
    fit.improvement_final = improvement_final
    fit.rate_projected = rate_projected
    return fit


def _extrapolate_gamma(
    gamma: np.ndarray,
    cohorts: np.ndarray,
    ages: np.ndarray,
    projection_years: np.ndarray,
    *,
    mode: Literal["flat", "last_drift"] = "last_drift",
) -> tuple[np.ndarray, np.ndarray]:
    """γ(c) を未観測コホート (投影期間で新しく発生する c) まで外挿。"""
    cohorts = np.asarray(cohorts, dtype=int)
    gamma = np.asarray(gamma, dtype=float)

    needed = np.unique(projection_years[:, np.newaxis] - ages[np.newaxis, :])
    all_cohorts = np.unique(np.concatenate([cohorts, needed]))
    out_gamma = np.zeros_like(all_cohorts, dtype=float)
    idx_known = {c: k for k, c in enumerate(cohorts)}

    c_max_known = int(cohorts.max())
    c_min_known = int(cohorts.min())
    last_drift = gamma[-1] - gamma[-2] if len(gamma) >= 2 else 0.0
    first_drift = gamma[1] - gamma[0] if len(gamma) >= 2 else 0.0

    for k, c in enumerate(all_cohorts):
        c_int = int(c)
        if c_int in idx_known:
            out_gamma[k] = gamma[idx_known[c_int]]
        elif c_int > c_max_known:
            steps = c_int - c_max_known
            if mode == "flat":
                out_gamma[k] = gamma[-1]
            else:
                out_gamma[k] = gamma[-1] + last_drift * steps
        else:
            steps = c_min_known - c_int
            if mode == "flat":
                out_gamma[k] = gamma[0]
            else:
                out_gamma[k] = gamma[0] - first_drift * steps
    return out_gamma, all_cohorts


__all__ = [
    "ScaleBBAPCConfig",
    "ScaleBBAPCFitResult",
    "cohort_year_step",
    "diagonal_difference_matrix",
    "whittaker_henderson_apc",
    "decompose_apc_additive",
    "build_covid_weight",
    "fit_scale_bb_apc",
    "project_scale_bb_apc",
]
