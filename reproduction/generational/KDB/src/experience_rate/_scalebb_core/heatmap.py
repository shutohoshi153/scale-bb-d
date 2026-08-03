"""Generate Scale BB style age x calendar-year heatmaps per disease.

As in Figures 1-5 of the original SOA paper, improvement rates (year-over-year)
are rendered as heatmaps with a bipolar colormap (*green = large improvement,
red = small improvement*). This script emits the following two kinds of
visualizations.

1. **Observed improvement-rate heatmap**
   - Input: ``mortality_apc_panel`` (mortality) or ``age_period_panel`` (utilization rate)
   - Plots annualized improvement rates on the **sparse year grid** as-is
2. **Improvement-rate heatmap after applying Scale BB (observed smoothing + long-term convergence)**
   - Internally computes matrices equivalent to the results of
     ``scripts/scale_bb_disease.py fit/project`` and places the smoothed
     improvement rates alongside the Phase 2 results gradually converged to
     the long-term rate L

Usage::

    # Scale BB mortality heatmaps for 3 diseases (cancer/heart_disease/cerebrovascular)
    python scripts/visualize_scale_bb_heatmaps.py \
        --source mortality --sex total --age-min 40 --age-max 89 \
        --year-min 1990 --output-dir figures/

    # Heatmap of utilization rates (age_period_panel, all diseases combined)
    python scripts/visualize_scale_bb_heatmaps.py \
        --source age_period --sex total --section total \
        --age-min 5 --age-max 85 --output-dir figures/
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

matplotlib.use("Agg")

from ..db import PROJECT_ROOT as ROOT
from .model import (
    ScaleBBConfig,
    fit_scale_bb,
    project_scale_bb,
)
from .panels import load_age_period_matrix, load_mortality_matrix


def _rel_to_root(path: Path) -> str:
    """Display relative to ``ROOT`` if under it, otherwise absolute."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


# Colorbar range (± one-sided pct). Follows the heat maps of the original Scale BB paper.
IMPROVEMENT_VMAX = 0.05


def _try_set_japanese_font() -> None:
    """Simple workaround to avoid garbled Japanese labels on Windows."""
    for family in ["Yu Gothic", "MS Gothic", "Meiryo", "Hiragino Sans", "IPAexGothic"]:
        try:
            matplotlib.font_manager.findfont(family, fallback_to_default=False)
            matplotlib.rcParams["font.family"] = family
            break
        except Exception:
            continue
    matplotlib.rcParams["axes.unicode_minus"] = False


def plot_improvement_heatmap(
    improvement: np.ndarray,
    ages: np.ndarray,
    years: np.ndarray,
    *,
    title: str,
    ax: plt.Axes,
    vmax: float = IMPROVEMENT_VMAX,
    cmap: str = "RdYlGn",
) -> matplotlib.image.AxesImage:
    """Draw the improvement-rate matrix onto an axis as a heatmap.

    Args:
        improvement: improvement rates of shape (n_age, n_year)
        ages: age array
        years: year array (observed or projection years)
        title: subplot title
        ax: target axes
        vmax: one-sided colormap limit (improvement rate ±vmax)
        cmap: matplotlib colormap name
    """
    ages = np.asarray(ages)
    years = np.asarray(years)
    # imshow puts (0,0) at the top-left. Flip so that age increases from bottom to top, which is easier to read.
    extent = [years.min() - 0.5, years.max() + 0.5, ages.min() - 0.5, ages.max() + 0.5]
    img = ax.imshow(
        improvement[::-1, :],
        aspect="auto",
        cmap=cmap,
        vmin=-vmax,
        vmax=vmax,
        interpolation="nearest",
        extent=extent,
    )
    ax.set_title(title, fontsize=11)
    ax.set_xlabel("Calendar year")
    ax.set_ylabel("Age")
    # Age labels: show all for 5-year steps, thin out if too many
    if ages.size <= 30:
        ax.set_yticks(ages)
    # Observation-year grid is irregularly spaced, so label years explicitly
    if years.size <= 30:
        ax.set_xticks(years)
        ax.set_xticklabels([str(int(y)) for y in years], rotation=45, fontsize=7)
    ax.grid(False)
    return img


def render_disease_heatmap(
    *,
    disease_id: str,
    rates: np.ndarray,
    ages: np.ndarray,
    years: np.ndarray,
    config: ScaleBBConfig,
    output_path: Path,
) -> None:
    """Generate a 3-panel heatmap (observed / smoothed / Scale BB projection) for one disease."""
    fit = fit_scale_bb(rates, ages=ages, years=years, config=config)
    fit = project_scale_bb(fit)

    fig, axes = plt.subplots(3, 1, figsize=(12, 14), constrained_layout=True)

    img0 = plot_improvement_heatmap(
        fit.improvement_observed,
        ages=ages,
        years=years,
        title=f"{disease_id}: Observed annual improvement (raw)",
        ax=axes[0],
    )
    img1 = plot_improvement_heatmap(
        fit.improvement_smoothed,
        ages=ages,
        years=years,
        title=(
            f"{disease_id}: Smoothed (Whittaker-Henderson 2D, "
            f"λ_age={config.lam_row}, λ_year={config.lam_col})"
        ),
        ax=axes[1],
    )
    img2 = plot_improvement_heatmap(
        fit.improvement_final,
        ages=ages,
        years=fit.projection_years,
        title=(
            f"{disease_id}: Scale BB blended (L={config.long_term_rate:.1%}, "
            f"P={config.convergence_year})"
        ),
        ax=axes[2],
    )

    for img, ax in [(img0, axes[0]), (img1, axes[1]), (img2, axes[2])]:
        fig.colorbar(img, ax=ax, shrink=0.8, label="Annual improvement rate")

    fig.suptitle(
        f"Scale BB style improvement heatmap - {disease_id}",
        fontsize=14,
        fontweight="bold",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"[saved] {_rel_to_root(output_path)}  "
          f"({rates.shape[0]} ages × {rates.shape[1]} years)")


def render_rate_trajectory(
    *,
    disease_id: str,
    ages: np.ndarray,
    years: np.ndarray,
    rates: np.ndarray,
    config: ScaleBBConfig,
    output_path: Path,
    ages_to_plot: tuple[int, ...] = (50, 60, 70, 80),
) -> None:
    """Line chart combining observed + projected rate time series for selected age bands into one figure."""
    fit = fit_scale_bb(rates, ages=ages, years=years, config=config)
    fit = project_scale_bb(fit)

    fig, ax = plt.subplots(figsize=(11, 6), constrained_layout=True)
    for a in ages_to_plot:
        if a not in ages:
            # use the nearest available age
            idx = int(np.argmin(np.abs(ages - a)))
        else:
            idx = int(np.where(ages == a)[0][0])
        age_val = int(ages[idx])
        ax.plot(
            fit.years,
            fit.rate_observed[idx, :],
            marker="o",
            linestyle=":",
            label=f"age {age_val} observed",
        )
        ax.plot(
            fit.projection_years,
            fit.rate_projected[idx, :],
            linestyle="-",
            label=f"age {age_val} BB projection",
        )
    last_obs = (
        config.last_observed_year
        if config.last_observed_year is not None
        else int(years.max())
    )
    ax.axvline(last_obs + 0.5, color="gray", linestyle="--", linewidth=1, label="last observed")
    ax.axvline(
        config.convergence_year, color="red", linestyle="--", linewidth=1,
        label=f"convergence {config.convergence_year}",
    )
    ax.set_yscale("log")
    ax.set_xlabel("Calendar year")
    ax.set_ylabel("Rate (per 100,000, log scale)")
    ax.set_title(f"{disease_id}: observed vs Scale BB projected rate")
    ax.legend(loc="best", fontsize=8, ncols=2)
    ax.grid(True, which="both", alpha=0.3)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"[saved] {_rel_to_root(output_path)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scale BB style improvement-rate heatmap visualization"
    )
    parser.add_argument(
        "--source",
        choices=["mortality", "age_period"],
        default="mortality",
    )
    parser.add_argument(
        "--disease",
        nargs="*",
        default=None,
        help="disease_id when source=mortality (default: cancer heart_disease cerebrovascular)",
    )
    parser.add_argument("--sex", default="total", choices=["total", "male", "female"])
    parser.add_argument(
        "--section",
        default="total",
        choices=["total", "inpatient", "outpatient"],
    )
    parser.add_argument("--age-min", type=int, default=20)
    parser.add_argument("--age-max", type=int, default=89)
    parser.add_argument("--year-min", type=int, default=None)
    parser.add_argument("--year-max", type=int, default=None)
    parser.add_argument("--lam-row", type=float, default=40.0)
    parser.add_argument("--lam-col", type=float, default=40.0)
    parser.add_argument("--long-term-rate", type=float, default=0.01)
    parser.add_argument("--convergence-year", type=int, default=2035)
    parser.add_argument("--horizon", type=int, default=2050)
    parser.add_argument(
        "--output-dir",
        default="figures",
        help="output directory (default: figures/)",
    )

    args = parser.parse_args(argv)
    _try_set_japanese_font()

    cfg = ScaleBBConfig(
        long_term_rate=args.long_term_rate,
        convergence_year=args.convergence_year,
        horizon_year=args.horizon,
        lam_row=args.lam_row,
        lam_col=args.lam_col,
    )
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir

    if args.source == "mortality":
        disease_ids = args.disease or ["cancer", "heart_disease", "cerebrovascular"]
        matrices = load_mortality_matrix(
            disease_ids=disease_ids,
            sex=args.sex,
            age_min=args.age_min,
            age_max=args.age_max,
            year_min=args.year_min,
            year_max=args.year_max,
        )
        for did, (ages, years, rates) in matrices.items():
            heatmap_path = output_dir / f"disease_improvement_heatmap_{did}_{args.sex}.png"
            traj_path = output_dir / f"disease_rate_trajectory_{did}_{args.sex}.png"
            render_disease_heatmap(
                disease_id=did,
                rates=rates,
                ages=ages,
                years=years,
                config=cfg,
                output_path=heatmap_path,
            )
            render_rate_trajectory(
                disease_id=did,
                ages=ages,
                years=years,
                rates=rates,
                config=cfg,
                output_path=traj_path,
            )
    elif args.source == "age_period":
        ages, years, rates = load_age_period_matrix(
            sex=args.sex,
            section=args.section,
            age_min=args.age_min,
            age_max=args.age_max,
            year_min=args.year_min,
            year_max=args.year_max,
        )
        did = f"patient_all_{args.section}"
        render_disease_heatmap(
            disease_id=did,
            rates=rates,
            ages=ages,
            years=years,
            config=cfg,
            output_path=output_dir / f"disease_improvement_heatmap_{did}_{args.sex}.png",
        )
        render_rate_trajectory(
            disease_id=did,
            ages=ages,
            years=years,
            rates=rates,
            config=cfg,
            output_path=output_dir / f"disease_rate_trajectory_{did}_{args.sex}.png",
        )
    else:
        parser.error(f"unknown --source: {args.source}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
