"""Scale BB 拡張アルゴリズムのコアライブラリ.

SOA (2012) の *Mortality Improvement Scale BB* 思想を疾病発生率に応用する際の
数理コアを切り出したモジュール。UI/CLI/DB ロード層から独立した純粋関数群として
実装し、以下の再利用先から直接呼び出される::

    scripts/scale_bb_disease.py             ... 研究用 CLI (fit + project)
    scripts/visualize_scale_bb_heatmaps.py  ... 研究用 可視化 CLI
    EAS/src/experience_rate/scalebb.py      ... EAS 側ラッパ (DB ロード含む)

原論文 Section 5.2 Phase 1 のアウトラインに準拠する::

    1. 実績率 m(x, t) を 2 次元平滑化（SOA は P-spline、本実装は等価な
       Whittaker-Henderson 差分罰則スムーザ）して改善率 i(x, t) を抽出
    2. 長期想定改善率 L と収束年 P を指定し、観測終端→P 年までの線形収束で
       2 次元改善率配列 i*(x, t) を合成
    3. 基準年 t0 からの累積で将来率 m(x, t) を投影
       m(x, t) = m(x, t0) * prod_{s=t0+1}^{t} (1 - i*(x, s))

観測年が不等間隔（例: 1950/1955/.../2005/2010/2013-2024）でも正しく
**年率ベース** の改善率に換算するため、`years` 配列は明示的に受け取って
ギャップを反映する。
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable

import numpy as np
from scipy.sparse import csr_matrix, diags, eye, kron
from scipy.sparse.linalg import spsolve


# ---------------------------------------------------------------------------
# 1. 2D Whittaker-Henderson smoother (P-spline 等価)
# ---------------------------------------------------------------------------
def _difference_matrix(n: int, d: int) -> csr_matrix:
    """``d`` 階差分行列 ``D`` (shape = (n-d, n)) を疎行列で構築."""
    if d < 1 or d >= n:
        raise ValueError(f"invalid diff order d={d} for n={n}")
    m = np.eye(n)
    for _ in range(d):
        m = np.diff(m, axis=0)
    return csr_matrix(m)


def whittaker_henderson_2d(
    y: np.ndarray,
    *,
    weight: np.ndarray | None = None,
    lam_row: float = 10.0,
    lam_col: float = 10.0,
    diff_order: int = 2,
) -> np.ndarray:
    """2 次元 Whittaker-Henderson スムーザ。

    目的関数::

        min_Z  sum_{i,j} w_{ij} (y_{ij} - z_{ij})^2
               + lam_row * ||D_d Z||_F^2
               + lam_col * ||Z D_d^T||_F^2

    ここで ``D_d`` は ``diff_order`` 階差分行列。SOA Scale BB の P-spline 平滑化
    （tensor-product B-spline + 差分罰則）とほぼ等価で、実装が単純かつ
    年齢・暦年の粗いグリッド（最大でも 80 × 80 程度）でも瞬時に収束する。

    Args:
        y: shape (n_row, n_col) の観測値行列。NaN は ``weight=0`` 扱いで補間。
        weight: 同 shape の重み行列。NaN 要素は自動的に 0 にクリップ。
        lam_row: 行方向（年齢）の平滑化パラメータ (正の実数)
        lam_col: 列方向（暦年）の平滑化パラメータ (正の実数)
        diff_order: 差分罰則の階数 (通常 2)

    Returns:
        shape (n_row, n_col) の平滑化後行列。
    """
    y = np.asarray(y, dtype=float)
    if y.ndim != 2:
        raise ValueError("y must be 2-D")
    n_row, n_col = y.shape

    if weight is None:
        weight = np.ones_like(y)
    weight = np.asarray(weight, dtype=float).copy()

    # NaN セルは重み 0 で平滑化対象から除外し、穴埋めは罰則項任せ
    nan_mask = ~np.isfinite(y)
    y = np.where(nan_mask, 0.0, y)
    weight[nan_mask] = 0.0
    weight = np.where(np.isfinite(weight) & (weight >= 0), weight, 0.0)

    # vec(Z) は Fortran (column-major) で整列 → vec(Z)[i + n_row*j] = Z[i, j]
    w_vec = weight.flatten(order="F")
    y_vec = y.flatten(order="F")

    d_row = _difference_matrix(n_row, diff_order)
    d_col = _difference_matrix(n_col, diff_order)
    p_row = kron(eye(n_col, format="csr"), (d_row.T @ d_row), format="csr")
    p_col = kron((d_col.T @ d_col), eye(n_row, format="csr"), format="csr")

    w_diag = diags(w_vec, 0, format="csr")
    a = (w_diag + lam_row * p_row + lam_col * p_col).tocsc()
    b = w_vec * y_vec
    z_vec = spsolve(a, b)
    return z_vec.reshape((n_row, n_col), order="F")


# ---------------------------------------------------------------------------
# 1b. Annual-grid expansion for unevenly spaced observation years
# ---------------------------------------------------------------------------
def expand_to_annual_grid(
    values: np.ndarray,
    years: np.ndarray,
    *,
    weight: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """観測年が不等間隔 (例: 1950, 1955, ..., 2010, 2013, 2014) の行列を、
    暦年の連続グリッド (min..max) に展開する。

    [FIX 2026-09-02] 差分行列 ``_difference_matrix`` は列インデックス基準のため、
    不等間隔の観測列をそのまま渡すと 5 年刻み区間の変化量が 1 年区間に持ち込まれ、
    グリッド切替点 (2010→2013→2014) で末端改善率が 3〜5 倍過大になっていた。
    欠測年を重み 0 の列として挿入すれば罰則が実際の 1 年刻みに対して働く
    (論文 §3.2.1 の定義通り)。

    Returns:
        (values_full, weight_full, full_years, obs_idx)
        ``obs_idx`` は ``full_years`` 上での観測年の位置 (平滑化後の再抽出用)。
    """
    values = np.asarray(values, dtype=float)
    years = np.asarray(years, dtype=int)
    full_years = np.arange(int(years.min()), int(years.max()) + 1)
    obs_idx = np.searchsorted(full_years, years)
    n_age = values.shape[0]
    values_full = np.full((n_age, full_years.size), np.nan)
    values_full[:, obs_idx] = values
    weight_full = np.zeros((n_age, full_years.size))
    if weight is None:
        weight_full[:, obs_idx] = np.where(np.isfinite(values), 1.0, 0.0)
    else:
        weight_full[:, obs_idx] = np.asarray(weight, dtype=float)
    return values_full, weight_full, full_years, obs_idx



# ---------------------------------------------------------------------------
# 2. Observed improvement rates (annualized for irregular year grids)
# ---------------------------------------------------------------------------
def compute_annual_improvement(
    rates: np.ndarray,
    years: np.ndarray,
) -> np.ndarray:
    """年率ベースの観測改善率行列を算出。

    年系列が不等間隔 (例: 1950, 1955, ..., 2013, 2014) でも、隣接 2 点間の
    幾何平均改善率に換算する::

        i_annual(x, t_k) = 1 - ( rate(x, t_k) / rate(x, t_{k-1}) )^{1 / (t_k - t_{k-1})}

    Args:
        rates: shape (n_age, n_year) の正値率行列 (NaN/負値可, 無効要素は NaN)
        years: 昇順の年配列 shape (n_year,)

    Returns:
        shape (n_age, n_year) の改善率行列。最初の年列は NaN。
    """
    rates = np.asarray(rates, dtype=float)
    years = np.asarray(years, dtype=float)
    if rates.shape[1] != years.size:
        raise ValueError("years length mismatch with rates columns")
    out = np.full_like(rates, np.nan)
    safe = np.where((rates > 0) & np.isfinite(rates), rates, np.nan)
    year_gaps = np.diff(years)
    if np.any(year_gaps <= 0):
        raise ValueError("years must be strictly increasing")
    ratio = safe[:, 1:] / safe[:, :-1]
    ratio = np.where(ratio > 0, ratio, np.nan)
    annual = 1.0 - ratio ** (1.0 / year_gaps)
    out[:, 1:] = annual
    return out


# ---------------------------------------------------------------------------
# 3. Scale BB core: blend observed improvements with long-term rate
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ScaleBBConfig:
    """Scale BB 拡張モデルの設定.

    `long_term_rate` (L) は原論文通常 1% (= 0.01)。`convergence_year` (P) は
    実績観測終端から先の年次で、`last_observed_year < convergence_year`。
    `cohort_convergence_years` は P と last_observed_year の差分として
    自動算出される。年齢別の長期率テーパ (age_taper_start / age_taper_end)
    を指定すると、指定範囲で L → 0 へ線形低減。
    """

    long_term_rate: float = 0.01
    convergence_year: int = 2035
    last_observed_year: int | None = None
    lam_row: float = 40.0
    lam_col: float = 40.0
    diff_order: int = 2
    age_taper_start: int | None = 90
    age_taper_end: int | None = 120
    horizon_year: int | None = None
    annual_grid: bool = True  # [FIX 2026-09-02] 平滑化を暦年連続グリッド上で行う (不等間隔対応)
    # [ADD 2026-09-03] 投影起点の水準 (論文 §3.2.2 式 3.6 の m(x, y_0))。
    #   "observed" : 基準年の観測率 (論文の記述どおり。既定)
    #   "smoothed" : 基準年の Phase 1 平滑化率 (2026-09-02 以前の実装)
    #   "mean_obs" : 直近 base_obs_points 観測点の観測率平均 (mean_3pts ベースラインと同じ水準アンカー)
    base_level: str = "observed"
    base_obs_points: int = 3
    # [ADD 2026-09-03] 収束期間 N (年)。指定時は P = last_observed_year + N とし convergence_year を上書きする。
    #   年次リフィット運用では暦年固定の P よりこちらが自然 (論文 §3.2.2 / §9.1)。
    convergence_period: int | None = None

    def effective_convergence_year(self, last_observed_year: int) -> int:
        """ブレンドの収束年 P。convergence_period 指定時は last_observed_year + N."""
        if self.convergence_period is not None:
            return int(last_observed_year) + int(self.convergence_period)
        return int(self.convergence_year)

    def taper_factor(self, age: int | float) -> float:
        """年齢別の長期率 テーパ係数 (1.0 → 0.0)."""
        if self.age_taper_start is None or self.age_taper_end is None:
            return 1.0
        if age <= self.age_taper_start:
            return 1.0
        if age >= self.age_taper_end:
            return 0.0
        span = max(self.age_taper_end - self.age_taper_start, 1)
        return max(0.0, 1.0 - (age - self.age_taper_start) / span)


def build_blended_improvements(
    smoothed_improvement: np.ndarray,
    years: np.ndarray,
    ages: np.ndarray,
    config: ScaleBBConfig,
) -> tuple[np.ndarray, np.ndarray]:
    """観測平滑化改善率と長期率 L を段階ブレンドした最終改善率を生成。

    原論文 Section 7.4 のブレンド関数 ``h(y)`` をそのまま採用::

        h(y) = 1.0                                 for y <= last_obs
        h(y) = linear( 1.0 → L_age/L ) in [last_obs+1, P-1]
        h(y) = L_age / L                           for y >= P

    投影期間は `last_observed_year+1` から `horizon_year` まで (デフォルトは
    `convergence_year + 15`)。実績期間では平滑化値をそのまま使う。

    Args:
        smoothed_improvement: shape (n_age, n_year) の平滑化済み改善率。
        years: 観測年配列 shape (n_year,)
        ages: 年齢配列 shape (n_age,)
        config: ScaleBBConfig

    Returns:
        (final_improvement, projection_years)  
        final_improvement: shape (n_age, n_project_year) で実績区間も含めた
            全期間改善率。
        projection_years: shape (n_project_year,) で投影対象年（実績 + 将来）。
    """
    ages_arr = np.asarray(ages, dtype=float)
    years_arr = np.asarray(years, dtype=int)
    last_obs = (
        int(config.last_observed_year)
        if config.last_observed_year is not None
        else int(years_arr.max())
    )
    horizon = (
        int(config.horizon_year)
        if config.horizon_year is not None
        else int(config.convergence_year + 15)
    )
    if horizon <= last_obs:
        horizon = last_obs + 1

    full_years = np.arange(int(years_arr.min()), horizon + 1)
    n_age = len(ages_arr)
    out = np.full((n_age, full_years.size), np.nan)

    # 実績区間: 観測年のみ既知。中間年は左隣の観測値で前進充填する (step-forward)
    year_index = {int(y): i for i, y in enumerate(years_arr)}
    last_obs_idx_in_smoothed = year_index[last_obs]
    for j, y in enumerate(full_years):
        y_int = int(y)
        if y_int <= last_obs:
            k = max(i for i in year_index.values() if years_arr[i] <= y_int)
            out[:, j] = smoothed_improvement[:, k]
        else:
            break

    # 観測終端の値 (改善率ベース) を blending の出発点に
    i_last = smoothed_improvement[:, last_obs_idx_in_smoothed]
    l_target = np.array(
        [config.long_term_rate * config.taper_factor(a) for a in ages_arr]
    )

    # 投影期間: linear blend in year domain (論文 Section 7.4 h(y))
    conv_year = config.effective_convergence_year(last_obs)  # [ADD 2026-09-03] convergence_period 対応
    for j, y in enumerate(full_years):
        y_int = int(y)
        if y_int <= last_obs:
            continue
        if y_int >= conv_year:
            out[:, j] = l_target
        else:
            denom = max(conv_year - last_obs, 1)
            t = (y_int - last_obs) / denom
            out[:, j] = (1.0 - t) * i_last + t * l_target

    return out, full_years


def project_rates(
    base_rates: np.ndarray,
    improvements: np.ndarray,
    base_year: int,
    years: np.ndarray,
) -> np.ndarray:
    """基準年率 × 改善率で将来率を累積生成。

    Args:
        base_rates: shape (n_age,) の基準年 (``base_year``) の率
        improvements: shape (n_age, n_year) の改善率行列
            列 ``k`` は ``years[k]`` の改善率 i(x, t_k)
        base_year: 基準年（``years[k]==base_year`` で ``m(x, base_year)=base_rates``）
        years: shape (n_year,) の年配列

    Returns:
        shape (n_age, n_year) の投影率行列。
    """
    base_rates = np.asarray(base_rates, dtype=float)
    years = np.asarray(years, dtype=int)
    if base_year not in years:
        raise ValueError(f"base_year {base_year} not in years")
    base_idx = int(np.where(years == base_year)[0][0])

    n_age, n_year = improvements.shape
    out = np.full((n_age, n_year), np.nan)
    out[:, base_idx] = base_rates

    # 前向き累積
    for k in range(base_idx + 1, n_year):
        prev = out[:, k - 1]
        imp = improvements[:, k]
        out[:, k] = prev * (1.0 - imp)
    # 後向き累積
    for k in range(base_idx - 1, -1, -1):
        nxt = out[:, k + 1]
        imp_next = improvements[:, k + 1]
        with np.errstate(divide="ignore", invalid="ignore"):
            out[:, k] = nxt / np.where(
                np.isfinite(1.0 - imp_next) & (1.0 - imp_next != 0),
                (1.0 - imp_next),
                np.nan,
            )
    return out


# ---------------------------------------------------------------------------
# 4. Convenience API: one-shot fit / project
# ---------------------------------------------------------------------------
@dataclass
class ScaleBBFitResult:
    """``fit_scale_bb`` の結果格納用データクラス."""

    ages: np.ndarray
    years: np.ndarray
    rate_observed: np.ndarray  # shape (n_age, n_year) observed rates
    rate_smoothed: np.ndarray  # shape (n_age, n_year) smoothed on log-scale
    improvement_observed: np.ndarray  # annualized observed improvement
    improvement_smoothed: np.ndarray  # smoothed improvement (Phase 1)
    config: ScaleBBConfig = field(default_factory=ScaleBBConfig)

    # 投影段で埋める
    projection_years: np.ndarray | None = None
    improvement_final: np.ndarray | None = None
    rate_projected: np.ndarray | None = None


def fit_scale_bb(
    rate_matrix: np.ndarray,
    ages: Iterable[int | float],
    years: Iterable[int],
    *,
    config: ScaleBBConfig | None = None,
    weight: np.ndarray | None = None,
) -> ScaleBBFitResult:
    """観測率行列 (age × year) に対し Scale BB Phase 1 平滑化を実行。

    [ADD 2026-09-30] ``weight`` (rate_matrix と同 shape、非負) を渡すと観測セルの重みに使う。
    死亡数を渡せば、対数率の分散が概ね 1/死亡数 であること (Poisson) に対応する重み付き平滑化になる
    (論文 §10 第 6 項の感度分析)。重みは観測セルの平均が 1 になるよう正規化するので、
    lam_row / lam_col の意味は等重み (weight=None、既定・論文の主結果) と揃う。

    率は log スケールで平滑化する（正値性を維持し、年齢・期間効果を乗法的に
    扱うため）。0 以下の値は NaN として扱う。

    Args:
        rate_matrix: shape (n_age, n_year) の率 (人口10万対でも無次元でも可)
        ages: 年齢配列
        years: 年配列 (昇順, 不等間隔可)
        config: ScaleBBConfig (None の場合はデフォルト)

    Returns:
        ScaleBBFitResult
    """
    cfg = config or ScaleBBConfig()
    ages_arr = np.asarray(list(ages), dtype=float)
    years_arr = np.asarray(list(years), dtype=int)
    rates = np.asarray(rate_matrix, dtype=float)

    if rates.shape != (ages_arr.size, years_arr.size):
        raise ValueError(
            f"rate_matrix shape {rates.shape} does not match "
            f"({ages_arr.size}, {years_arr.size})"
        )
    if np.any(np.diff(years_arr) <= 0):
        raise ValueError("years must be strictly increasing")

    # log 変換 (0/負は NaN 化して重み 0 扱いにする)
    with np.errstate(divide="ignore", invalid="ignore"):
        log_r = np.where(rates > 0, np.log(rates), np.nan)
    weight_obs = np.where(np.isfinite(log_r), 1.0, 0.0)
    if weight is not None:
        w = np.asarray(weight, dtype=float)
        if w.shape != rates.shape:
            raise ValueError(f"weight shape {w.shape} does not match rate_matrix {rates.shape}")
        w = np.where(np.isfinite(w) & (w > 0), w, 0.0) * weight_obs
        if w.sum() <= 0:
            raise ValueError("weight has no positive entry on observed cells")
        weight_obs = w * (np.count_nonzero(w) / w.sum())
    weight = weight_obs
    if cfg.annual_grid:
        # [FIX 2026-09-02] 欠測年を重み 0 の列として補い、暦年 1 年刻みで平滑化してから
        # 観測年の列だけを取り出す (出力 shape は従来通り (n_age, n_year))。
        log_r_full, weight_full, _full_years, obs_idx = expand_to_annual_grid(
            log_r, years_arr, weight=weight
        )
        log_r_smoothed = whittaker_henderson_2d(
            log_r_full,
            weight=weight_full,
            lam_row=cfg.lam_row,
            lam_col=cfg.lam_col,
            diff_order=cfg.diff_order,
        )[:, obs_idx]
    else:
        log_r_smoothed = whittaker_henderson_2d(
            log_r,
            weight=weight,
            lam_row=cfg.lam_row,
            lam_col=cfg.lam_col,
            diff_order=cfg.diff_order,
        )
    rate_smoothed = np.exp(log_r_smoothed)

    imp_obs = compute_annual_improvement(rates, years_arr)
    imp_smoothed = compute_annual_improvement(rate_smoothed, years_arr)

    return ScaleBBFitResult(
        ages=ages_arr,
        years=years_arr,
        rate_observed=rates,
        rate_smoothed=rate_smoothed,
        improvement_observed=imp_obs,
        improvement_smoothed=imp_smoothed,
        config=cfg,
    )


def select_base_rates(
    fit: "ScaleBBFitResult",
    base_year: int,
    base_level: str = "observed",
    base_obs_points: int = 3,
) -> np.ndarray:
    """投影起点 m(x, y_0) の水準を選ぶ ([ADD 2026-09-03], 論文 §3.2.2 式 3.6).

    - "observed": 基準年の観測率。観測が欠測/非正の年齢は平滑化率で補う。
    - "smoothed": 基準年の平滑化率 (旧実装)。
    - "mean_obs": 直近 ``base_obs_points`` 個の観測点 (基準年を含む、欠測年は数えない) の観測率平均。
    """
    j = int(np.where(fit.years == base_year)[0][0])
    smoothed = fit.rate_smoothed[:, j].copy()
    if base_level == "smoothed":
        return smoothed
    obs = fit.rate_observed
    if base_level == "observed":
        b = obs[:, j].copy()
    elif base_level == "mean_obs":
        n = max(int(base_obs_points), 1)
        cols = [k for k in range(j + 1) if np.any(np.isfinite(obs[:, k]) & (obs[:, k] > 0))][-n:]
        with np.errstate(invalid="ignore"):
            block = np.where(obs[:, cols] > 0, obs[:, cols], np.nan)
            b = np.nanmean(block, axis=1)
    else:
        raise ValueError(f"unknown base_level: {base_level!r}")
    bad = ~np.isfinite(b) | (b <= 0)
    b[bad] = smoothed[bad]
    return b


def project_scale_bb(
    fit: ScaleBBFitResult,
    *,
    base_year: int | None = None,
) -> ScaleBBFitResult:
    """Phase 2: 長期率ブレンド → 将来率投影。

    ``fit`` の ``projection_years`` / ``improvement_final`` / ``rate_projected``
    を埋めて返す（in-place）。

    Args:
        fit: ``fit_scale_bb`` の結果
        base_year: 投影起点となる基準年 (観測最終年がデフォルト)
    """
    cfg = fit.config
    last_obs = (
        int(cfg.last_observed_year)
        if cfg.last_observed_year is not None
        else int(fit.years.max())
    )
    cfg_effective = replace(cfg, last_observed_year=last_obs)
    improvement_final, projection_years = build_blended_improvements(
        fit.improvement_smoothed,
        years=fit.years,
        ages=fit.ages,
        config=cfg_effective,
    )

    base = base_year if base_year is not None else last_obs
    base_rates = select_base_rates(fit, base, cfg.base_level, cfg.base_obs_points)
    rate_projected = project_rates(
        base_rates,
        improvements=improvement_final,
        base_year=base,
        years=projection_years,
    )

    fit.projection_years = projection_years
    fit.improvement_final = improvement_final
    fit.rate_projected = rate_projected
    return fit


__all__ = [
    "ScaleBBConfig",
    "ScaleBBFitResult",
    "whittaker_henderson_2d",
    "compute_annual_improvement",
    "build_blended_improvements",
    "project_rates",
    "fit_scale_bb",
    "project_scale_bb",
    "select_base_rates",
]
