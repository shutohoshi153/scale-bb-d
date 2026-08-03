"""APC (Age-Period-Cohort) extension of the Scale BB extension model.

Extends the 2D Whittaker-Henderson smoothing of `scripts/scale_bb_model.py`
into an APC model by adding a **difference penalty along the diagonal
(cohort) direction**.

Mathematical summary
--------------------

- Original Scale BB (AP model): after 2D smoothing of log m(x, t), the
  improvement rates corresponding to ``β(t)`` are blended with the long-term
  rate L and projected. The cohort effect γ(c) is absorbed into the period effect.

- This extension (APC model): the objective function is changed as follows.
  By also adding second differences along the cohort = t - x direction as a
  penalty term, the "aging trajectory within the same birth cohort" is
  constrained to be smooth.

    J(Z) = Σ_{i,j} w_{ij} (log m_{ij} - Z_{ij})^2
         + λ_age    · || D_age^(d)  Z      ||_F^2   (age direction)
         + λ_period · || Z D_period^(d)^T  ||_F^2   (calendar-year direction)
         + λ_cohort · || D_cohort^(d) vec(Z) ||^2   (diagonal direction <- new)

- The COVID period (e.g. 2020-2022) can be handled in one of the following ways:
    * ``covid_mode="weight_down"``: lower the observation weights of COVID years to ``covid_weight``
      (suppresses smoothing from deviating from the long-term trend)
    * ``covid_mode="dummy"``: treat COVID years separately as period-effect dummies
      (post-fit, only the β(t) shift of the COVID years is extracted)
    * ``covid_mode="none"``: treat normally

Identifiability
---------------
Due to the linear relation Age + Period = Cohort, the absolute levels and
linear components of the three effects are unidentified.
Since this implementation uses a second-difference penalty, constant and
linear terms are automatically excluded from the penalty, and the additive
decomposition ``log m(x, t) = α(x) + β(t) + γ(c)`` is uniquely identified
only at the (second-)difference level (following the Holford 1983 framework).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import comb
from typing import Iterable, Literal

import numpy as np
from scipy.sparse import csr_matrix, diags, eye, kron, lil_matrix
from scipy.sparse.linalg import spsolve

from .model import (
    ScaleBBConfig,
    ScaleBBFitResult,
    _difference_matrix,
    build_blended_improvements,
    compute_annual_improvement,
    project_rates,
)


# ---------------------------------------------------------------------------
# Cohort (diagonal) difference matrix
# ---------------------------------------------------------------------------
def diagonal_difference_matrix(
    n_age: int,
    n_year: int,
    diff_order: int = 2,
) -> csr_matrix:
    """Order-``diff_order`` difference matrix along the diagonal (cohort = year − age) direction.

    ``vec(Z)`` assumes Fortran order (column-major, columns = years), i.e.
    ``vec(Z)[i + n_age * j] = Z[i, j]``. Advancing age i by 1 within the same
    cohort gives (i+1, j+1), so the order-d difference along the diagonal is
    defined as

        Σ_{k=0..d} (-1)^{d-k} C(d, k) · Z[i+k, j+k]

    The penalty term is the quadratic form ``|| D vec(Z) ||^2``.

    Args:
        n_age:   number of age classes
        n_year:  number of years
        diff_order: difference order (usually 2)

    Returns:
        Sparse matrix of shape = ((n_age - d) x (n_year - d), n_age * n_year).
    """
    d = diff_order
    if d < 1:
        raise ValueError("diff_order must be >= 1")
    if n_age <= d or n_year <= d:
        # If there are not enough cells in the cohort direction, return an empty matrix
        return csr_matrix((0, n_age * n_year))

    # Binomial coefficients (-1)^{d-k} * C(d, k)
    coefs = np.array([(-1) ** (d - k) * comb(d, k) for k in range(d + 1)], dtype=float)

    n_rows = (n_age - d) * (n_year - d)
    n_cols = n_age * n_year
    mat = lil_matrix((n_rows, n_cols))

    row_idx = 0
    for j in range(n_year - d):
        for i in range(n_age - d):
            for k in range(d + 1):
                col = (i + k) + n_age * (j + k)
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
) -> np.ndarray:
    """2D Whittaker-Henderson smoothing with a diagonal penalty (APC version).

    Args:
        y: observation matrix of shape (n_age, n_year) (NaN treated as weight 0)
        weight: weights of the same shape. If None, 1.0 for finite cells and 0.0 for NaN
        lam_age: smoothing parameter in the age (row) direction
        lam_period: smoothing parameter in the calendar-year (column) direction
        lam_cohort: smoothing parameter in the cohort (diagonal) direction (new)
        diff_order: difference order

    Returns:
        Smoothed matrix of shape (n_age, n_year).
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

    # vec(Z) is in F-order: vec(Z)[i + n_age * j] = Z[i, j]
    w_vec = weight.flatten(order="F")
    y_vec = y.flatten(order="F")

    d_age = _difference_matrix(n_age, diff_order)
    d_year = _difference_matrix(n_year, diff_order)
    d_cohort = diagonal_difference_matrix(n_age, n_year, diff_order=diff_order)

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
# APC additive decomposition: log m(x, t) = α(x) + β(t) + γ(c) + residual
# ---------------------------------------------------------------------------
def decompose_apc_additive(
    log_rate_smoothed: np.ndarray,
    ages: np.ndarray,
    years: np.ndarray,
    *,
    weight: np.ndarray | None = None,
    max_iter: int = 200,
    tol: float = 1e-8,
) -> dict[str, np.ndarray]:
    """Additively decompose the smoothed log rates into α(x) + β(t) + γ(c) (iterative weighted least squares).

    Reference constraints are imposed for identifiability:
    - α(x_ref) = 0  (x_ref = minimum age)
    - β(t_ref) = 0  (t_ref = minimum calendar year)
    - γ(c) referenced to zero second differences + the earliest cohort

    An ambiguity remains in how the linear component is distributed between
    period and cohort; this function follows the Holford convention of
    "assigning the intercept to period and the drift to year".

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
        # Update α(x) (β, γ fixed)
        for i in range(n_age):
            w_i = weight[i, :]
            if w_i.sum() == 0:
                continue
            g_i = np.array([gamma[cohort_idx[cohort_matrix[i, j]]] for j in range(n_year)])
            resid = y[i, :] - beta - g_i
            alpha[i] = np.sum(w_i * resid) / w_i.sum()
        # Update β(t)
        for j in range(n_year):
            w_j = weight[:, j]
            if w_j.sum() == 0:
                continue
            g_j = np.array([gamma[cohort_idx[cohort_matrix[i, j]]] for i in range(n_age)])
            resid = y[:, j] - alpha - g_j
            beta[j] = np.sum(w_j * resid) / w_j.sum()
        # Update γ(c)
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

        # Identification constraints: α(x_ref) = 0, β(t_ref) = 0
        # (constant and linear components of γ are unidentified, but centered for numerical stability)
        a_shift = alpha[0]
        alpha -= a_shift
        beta += a_shift  # absorb the intercept into β
        b_shift = beta[0]
        beta -= b_shift
        # Holford convention: the drift (linear part) of β is not pushed onto γ
        # Centering of γ: not forced to (weighted) mean 0 (preserves cohort drift)

        # Convergence check: weighted RSS
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
    """Generate the weight matrix for the COVID period.

    mode:
        - ``weight_down``: multiply observation weights of COVID years by ``covid_weight``
        - ``dummy`` / ``none``: return base_weight unchanged (dummy handling is done in another layer)
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
    """Configuration with additional parameters for the APC extension.

    ``lam_row`` / ``lam_col`` of ScaleBBConfig are reused as the smoothing λ
    in the age / calendar-year directions, respectively.
    Since ScaleBBConfig is frozen, this class also inherits with frozen=True.
    """

    lam_cohort: float = 40.0
    covid_years: tuple[int, ...] = (2020, 2021, 2022)
    covid_weight: float = 0.3
    covid_mode: Literal["weight_down", "dummy", "none"] = "weight_down"


@dataclass
class ScaleBBAPCFitResult(ScaleBBFitResult):
    """Extended class holding APC decomposition results."""

    alpha: np.ndarray | None = None      # α(age), shape (n_age,)
    beta: np.ndarray | None = None       # β(period), shape (n_year,)
    gamma: np.ndarray | None = None      # γ(cohort), shape (n_cohort,)
    cohorts: np.ndarray | None = None    # cohort labels (years)
    covid_adjustment: np.ndarray | None = None  # period shift of COVID years (if dummy mode)


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
    """APC-extended Scale BB Phase 1 fit.

    - APC smoothing on the log scale (including the diagonal penalty)
    - COVID years handled by weight-down or dummy
    - Compute the additive decomposition α/β/γ
    - Improvement rates are "annual differences from each of (observed, smoothed)", same format as the original Scale BB

    Returns:
        ScaleBBAPCFitResult (extends ScaleBBFitResult)
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

    log_r_smoothed = whittaker_henderson_apc(
        log_r,
        weight=weight,
        lam_age=cfg.lam_row,
        lam_period=cfg.lam_col,
        lam_cohort=cfg.lam_cohort,
        diff_order=cfg.diff_order,
    )
    rate_smoothed = np.exp(log_r_smoothed)

    imp_obs = compute_annual_improvement(rates, years_arr)
    imp_smoothed = compute_annual_improvement(rate_smoothed, years_arr)

    # Additive decomposition (smoothed log rates -> α + β + γ + residual)
    decomp = decompose_apc_additive(
        log_r_smoothed,
        ages=ages_arr.astype(int),
        years=years_arr,
        weight=weight,
    )

    # COVID dummy mode: replace β of COVID years with the non-COVID linear
    # interpolation value and extract the shift.
    # Important: the additive decomposition α + β + γ discards constant/linear
    # components due to the identification constraints (α[0]=0, β[0]=0), so
    # reconstructing directly as log_rate = α + β + γ would lose the absolute
    # level (e.g. a drastic transformation like log_rate=5 -> 0.5).
    # Therefore, correct by **subtracting only the COVID-period β shock from
    # the original log_r_smoothed**, preserving the absolute level.
    covid_adj = None
    if cfg.covid_mode == "dummy":
        beta = decomp["beta"].copy()
        mask_covid = np.array(
            [int(y) in set(cfg.covid_years) for y in years_arr], dtype=bool
        )
        idx_all = np.arange(len(years_arr))
        idx_non = idx_all[~mask_covid]
        if idx_non.size >= 2:
            poly = np.polyfit(years_arr[idx_non], beta[idx_non], deg=1)
            beta_trend = np.polyval(poly, years_arr)
            covid_adj = np.where(mask_covid, beta - beta_trend, 0.0)
            beta_corrected = np.where(mask_covid, beta_trend, beta)
            decomp["beta"] = beta_corrected

            # Subtract only the COVID shock (β - β_trend) in log space
            # -> absolute level, age-specific structure, and cohort effects are preserved as-is
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
) -> ScaleBBAPCFitResult:
    """Project APC fit results to future years.

    Projection strategy:
    1. Linearly converge the improvement rates i(x, t) to the long-term rate L, as in the original Scale BB
    2. Among the cohorts corresponding to projection years (= projection year − age),
       cohorts observed during the training period use γ(c);
       unobserved cohorts (= newly emerging cohorts) follow ``cohort_extrapolation``:
         - "flat"        : γ(c) = last observed γ
         - "last_drift"  : extrapolate the first difference at the tail of γ(c) (linear extension)
    3. Projected rate = α + β(projected) + γ(c) added in log space -> back to rate space via exp
       However, base_year is unified to cumulative projection from observed crude rates (along the improvement-rate path)

    Note: to stay consistent with the AP-style improvement-rate projection
    (existing Scale BB), this function adopts
    rate_projected = project_rates(base_rates=rate_smoothed@base_year, improvement=i*).
    The α/β/γ decomposition is retained for interpretation/reporting purposes.
    """
    cfg: ScaleBBAPCConfig = fit.config  # type: ignore[assignment]
    last_obs = (
        int(cfg.last_observed_year)
        if cfg.last_observed_year is not None
        else int(fit.years.max())
    )
    improvement_final, projection_years = build_blended_improvements(
        fit.improvement_smoothed,
        years=fit.years,
        ages=fit.ages,
        config=ScaleBBConfig(
            long_term_rate=cfg.long_term_rate,
            convergence_year=cfg.convergence_year,
            last_observed_year=last_obs,
            lam_row=cfg.lam_row,
            lam_col=cfg.lam_col,
            diff_order=cfg.diff_order,
            age_taper_start=cfg.age_taper_start,
            age_taper_end=cfg.age_taper_end,
            horizon_year=cfg.horizon_year,
        ),
    )

    base = base_year if base_year is not None else last_obs
    base_rates = fit.rate_smoothed[:, int(np.where(fit.years == base)[0][0])].copy()
    rate_projected = project_rates(
        base_rates, improvements=improvement_final, base_year=base, years=projection_years
    )

    fit.projection_years = projection_years
    fit.improvement_final = improvement_final
    fit.rate_projected = rate_projected

    # Cohort extrapolation (unobserved part of γ(c))
    if fit.gamma is not None and fit.cohorts is not None:
        fit.gamma = _extrapolate_gamma(
            fit.gamma,
            fit.cohorts,
            fit.ages.astype(int),
            projection_years,
            mode=cohort_extrapolation,
        )[0]
        fit.cohorts = _extrapolate_gamma(
            fit.gamma, fit.cohorts, fit.ages.astype(int), projection_years, mode=cohort_extrapolation
        )[1]

    return fit


def _extrapolate_gamma(
    gamma: np.ndarray,
    cohorts: np.ndarray,
    ages: np.ndarray,
    projection_years: np.ndarray,
    *,
    mode: Literal["flat", "last_drift"] = "last_drift",
) -> tuple[np.ndarray, np.ndarray]:
    """Extrapolate γ(c) to unobserved cohorts (c newly arising during the projection period)."""
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
    "diagonal_difference_matrix",
    "whittaker_henderson_apc",
    "decompose_apc_additive",
    "build_covid_weight",
    "fit_scale_bb_apc",
    "project_scale_bb_apc",
]
