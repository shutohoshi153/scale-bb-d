"""Core library of the Scale BB extension algorithm.

Module extracting the mathematical core used when applying the SOA (2012)
*Mortality Improvement Scale BB* philosophy to disease incidence rates.
Implemented as pure functions independent of the UI/CLI/DB loading layers,
and called directly from the following reuse sites::

    scripts/scale_bb_disease.py             ... research CLI (fit + project)
    scripts/visualize_scale_bb_heatmaps.py  ... research visualization CLI
    KDB/src/experience_rate/scalebb.py      ... KDB-side wrapper (incl. DB loading)

Follows the outline of Section 5.2 Phase 1 of the original paper::

    1. Smooth the observed rates m(x, t) in 2-D (SOA uses P-splines; this
       implementation uses an equivalent Whittaker-Henderson difference-penalty
       smoother) and extract improvement rates i(x, t)
    2. Given the long-term assumed improvement rate L and convergence year P,
       compose the 2-D improvement-rate array i*(x, t) by linear convergence
       from the end of observation to year P
    3. Project future rates m(x, t) by cumulating from base year t0
       m(x, t) = m(x, t0) * prod_{s=t0+1}^{t} (1 - i*(x, s))

Even with irregularly spaced observation years (e.g. 1950/1955/.../2005/2010/
2013-2024), the `years` array is passed explicitly so that gaps are reflected
and improvement rates are correctly converted to an **annualized** basis.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
from scipy.sparse import csr_matrix, diags, eye, kron
from scipy.sparse.linalg import spsolve


# ---------------------------------------------------------------------------
# 1. 2D Whittaker-Henderson smoother (P-spline equivalent)
# ---------------------------------------------------------------------------
def _difference_matrix(n: int, d: int) -> csr_matrix:
    """Build the order-``d`` difference matrix ``D`` (shape = (n-d, n)) as a sparse matrix."""
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
    """2-D Whittaker-Henderson smoother.

    Objective function::

        min_Z  sum_{i,j} w_{ij} (y_{ij} - z_{ij})^2
               + lam_row * ||D_d Z||_F^2
               + lam_col * ||Z D_d^T||_F^2

    where ``D_d`` is the order-``diff_order`` difference matrix. Nearly
    equivalent to the SOA Scale BB P-spline smoothing (tensor-product B-spline
    + difference penalty), simpler to implement, and converges instantly even
    on coarse age x calendar-year grids (at most ~80 x 80).

    Args:
        y: observation matrix of shape (n_row, n_col). NaN is treated as ``weight=0`` and interpolated.
        weight: weight matrix of the same shape. NaN elements are automatically clipped to 0.
        lam_row: smoothing parameter in the row direction (age) (positive real)
        lam_col: smoothing parameter in the column direction (calendar year) (positive real)
        diff_order: order of the difference penalty (usually 2)

    Returns:
        Smoothed matrix of shape (n_row, n_col).
    """
    y = np.asarray(y, dtype=float)
    if y.ndim != 2:
        raise ValueError("y must be 2-D")
    n_row, n_col = y.shape

    if weight is None:
        weight = np.ones_like(y)
    weight = np.asarray(weight, dtype=float).copy()

    # NaN cells get weight 0 and are excluded from smoothing; gap-filling is left to the penalty term
    nan_mask = ~np.isfinite(y)
    y = np.where(nan_mask, 0.0, y)
    weight[nan_mask] = 0.0
    weight = np.where(np.isfinite(weight) & (weight >= 0), weight, 0.0)

    # vec(Z) is arranged in Fortran (column-major) order -> vec(Z)[i + n_row*j] = Z[i, j]
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
# 2. Observed improvement rates (annualized for irregular year grids)
# ---------------------------------------------------------------------------
def compute_annual_improvement(
    rates: np.ndarray,
    years: np.ndarray,
) -> np.ndarray:
    """Compute the annualized observed improvement-rate matrix.

    Even when the year series is irregularly spaced (e.g. 1950, 1955, ...,
    2013, 2014), convert to the geometric-mean improvement rate between
    adjacent points::

        i_annual(x, t_k) = 1 - ( rate(x, t_k) / rate(x, t_{k-1}) )^{1 / (t_k - t_{k-1})}

    Args:
        rates: positive-rate matrix of shape (n_age, n_year) (NaN/negative allowed; invalid elements become NaN)
        years: ascending year array of shape (n_year,)

    Returns:
        Improvement-rate matrix of shape (n_age, n_year). The first year column is NaN.
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
    """Configuration for the Scale BB extension model.

    `long_term_rate` (L) is usually 1% (= 0.01) as in the original paper.
    `convergence_year` (P) is a year beyond the end of observation, with
    `last_observed_year < convergence_year`.
    `cohort_convergence_years` is derived automatically as the difference
    between P and last_observed_year. If an age-specific long-term-rate taper
    (age_taper_start / age_taper_end) is specified, L is linearly reduced
    to 0 over the specified range.
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

    def taper_factor(self, age: int | float) -> float:
        """Age-specific long-term-rate taper factor (1.0 -> 0.0)."""
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
    """Generate final improvement rates by gradually blending the smoothed observed improvements with the long-term rate L.

    Adopts the blending function ``h(y)`` from Section 7.4 of the original paper as-is::

        h(y) = 1.0                                 for y <= last_obs
        h(y) = linear( 1.0 -> L_age/L ) in [last_obs+1, P-1]
        h(y) = L_age / L                           for y >= P

    The projection period runs from `last_observed_year+1` to `horizon_year`
    (default `convergence_year + 15`). Within the observed period the smoothed
    values are used as-is.

    Args:
        smoothed_improvement: smoothed improvement rates of shape (n_age, n_year).
        years: observed year array of shape (n_year,)
        ages: age array of shape (n_age,)
        config: ScaleBBConfig

    Returns:
        (final_improvement, projection_years)
        final_improvement: shape (n_age, n_project_year); improvement rates over
            the full period including the observed interval.
        projection_years: shape (n_project_year,); projection target years (observed + future).
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

    # Observed interval: only observation years are known. Intermediate years are forward-filled from the nearest observation to the left (step-forward)
    year_index = {int(y): i for i, y in enumerate(years_arr)}
    last_obs_idx_in_smoothed = year_index[last_obs]
    for j, y in enumerate(full_years):
        y_int = int(y)
        if y_int <= last_obs:
            k = max(i for i in year_index.values() if years_arr[i] <= y_int)
            out[:, j] = smoothed_improvement[:, k]
        else:
            break

    # Use the value at the end of observation (improvement-rate basis) as the blending starting point
    i_last = smoothed_improvement[:, last_obs_idx_in_smoothed]
    l_target = np.array(
        [config.long_term_rate * config.taper_factor(a) for a in ages_arr]
    )

    # Projection period: linear blend in year domain (paper Section 7.4 h(y))
    conv_year = int(config.convergence_year)
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
    """Cumulatively generate future rates as base-year rates x improvement rates.

    Args:
        base_rates: rates at the base year (``base_year``), shape (n_age,)
        improvements: improvement-rate matrix of shape (n_age, n_year)
            column ``k`` is the improvement rate i(x, t_k) for ``years[k]``
        base_year: base year (``m(x, base_year)=base_rates`` where ``years[k]==base_year``)
        years: year array of shape (n_year,)

    Returns:
        Projected-rate matrix of shape (n_age, n_year).
    """
    base_rates = np.asarray(base_rates, dtype=float)
    years = np.asarray(years, dtype=int)
    if base_year not in years:
        raise ValueError(f"base_year {base_year} not in years")
    base_idx = int(np.where(years == base_year)[0][0])

    n_age, n_year = improvements.shape
    out = np.full((n_age, n_year), np.nan)
    out[:, base_idx] = base_rates

    # Forward accumulation
    for k in range(base_idx + 1, n_year):
        prev = out[:, k - 1]
        imp = improvements[:, k]
        out[:, k] = prev * (1.0 - imp)
    # Backward accumulation
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
    """Dataclass holding the results of ``fit_scale_bb``."""

    ages: np.ndarray
    years: np.ndarray
    rate_observed: np.ndarray  # shape (n_age, n_year) observed rates
    rate_smoothed: np.ndarray  # shape (n_age, n_year) smoothed on log-scale
    improvement_observed: np.ndarray  # annualized observed improvement
    improvement_smoothed: np.ndarray  # smoothed improvement (Phase 1)
    config: ScaleBBConfig = field(default_factory=ScaleBBConfig)

    # Filled in at the projection stage
    projection_years: np.ndarray | None = None
    improvement_final: np.ndarray | None = None
    rate_projected: np.ndarray | None = None


def fit_scale_bb(
    rate_matrix: np.ndarray,
    ages: Iterable[int | float],
    years: Iterable[int],
    *,
    config: ScaleBBConfig | None = None,
) -> ScaleBBFitResult:
    """Run Scale BB Phase 1 smoothing on the observed rate matrix (age x year).

    Rates are smoothed on the log scale (to preserve positivity and treat
    age/period effects multiplicatively). Values <= 0 are treated as NaN.

    Args:
        rate_matrix: rates of shape (n_age, n_year) (per 100,000 population or dimensionless)
        ages: age array
        years: year array (ascending; irregular spacing allowed)
        config: ScaleBBConfig (defaults used if None)

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

    # log transform (0/negative values become NaN and are treated as weight 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        log_r = np.where(rates > 0, np.log(rates), np.nan)
    weight = np.where(np.isfinite(log_r), 1.0, 0.0)
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


def project_scale_bb(
    fit: ScaleBBFitResult,
    *,
    base_year: int | None = None,
) -> ScaleBBFitResult:
    """Phase 2: long-term-rate blending -> future-rate projection.

    Fills in ``projection_years`` / ``improvement_final`` / ``rate_projected``
    on ``fit`` and returns it (in-place).

    Args:
        fit: result of ``fit_scale_bb``
        base_year: base year from which to project (defaults to the last observed year)
    """
    cfg = fit.config
    last_obs = (
        int(cfg.last_observed_year)
        if cfg.last_observed_year is not None
        else int(fit.years.max())
    )
    cfg_effective = ScaleBBConfig(
        long_term_rate=cfg.long_term_rate,
        convergence_year=cfg.convergence_year,
        last_observed_year=last_obs,
        lam_row=cfg.lam_row,
        lam_col=cfg.lam_col,
        diff_order=cfg.diff_order,
        age_taper_start=cfg.age_taper_start,
        age_taper_end=cfg.age_taper_end,
        horizon_year=cfg.horizon_year,
    )
    improvement_final, projection_years = build_blended_improvements(
        fit.improvement_smoothed,
        years=fit.years,
        ages=fit.ages,
        config=cfg_effective,
    )

    base = base_year if base_year is not None else last_obs
    base_rates = fit.rate_smoothed[
        :, int(np.where(fit.years == base)[0][0])
    ].copy()
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
]
