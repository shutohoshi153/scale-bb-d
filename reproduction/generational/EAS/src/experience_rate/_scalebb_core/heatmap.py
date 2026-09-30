"""Scale BB スタイルの年齢 × 暦年ヒートマップを疾病別に生成する。

SOA 原論文 Figure 1-5 と同様、改善率 (year-over-year) を *緑=改善大、赤=改善小*
の二極性カラーマップでヒートマップ化する。本スクリプトは以下の 2 種の可視化を
吐き出す。

1. **観測改善率ヒートマップ**
   - 入力: ``mortality_apc_panel`` (死亡率) または ``age_period_panel`` (受療率)
   - 年率化改善率を **疎な年グリッド** のままプロット
2. **Scale BB 適用後の改善率ヒートマップ (実績平滑化 + 長期収束)**
   - ``scripts/scale_bb_disease.py fit/project`` 結果に相当する行列を内部で算出し、
     平滑化後改善率と、長期率 L に段階収束した Phase 2 結果を並べる

使い方::

    # 3 疾病 (cancer/heart_disease/cerebrovascular) の死亡率 Scale BB ヒートマップ
    python scripts/visualize_scale_bb_heatmaps.py \
        --source mortality --sex total --age-min 40 --age-max 89 \
        --year-min 1990 --output-dir figures/

    # 受療率 (age_period_panel 全疾病合算) のヒートマップ
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
    """``ROOT`` 配下なら相対表示、外なら絶対表示."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


# カラーバーのレンジ (± 片側 pct). Scale BB 原論文の heat map に倣う。
IMPROVEMENT_VMAX = 0.05


def _try_set_japanese_font() -> None:
    """Windows 環境で日本語ラベルを文字化けさせない簡易対応."""
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
    """改善率行列を axis にヒートマップとして描画する。

    Args:
        improvement: shape (n_age, n_year) の改善率
        ages: 年齢配列
        years: 年配列 (観測または投影年)
        title: サブプロットタイトル
        ax: 描画対象
        vmax: カラーマップの片側上限 (改善率 ±vmax)
        cmap: matplotlib カラーマップ名
    """
    ages = np.asarray(ages)
    years = np.asarray(years)
    # imshow は左上が (0,0)。年齢は下から上に大きくなる配置が分かりやすいので反転。
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
    # 年齢ラベル: 5 歳刻みなら全て表示、多い場合は間引く
    if ages.size <= 30:
        ax.set_yticks(ages)
    # 観測年グリッドは不等間隔なので年を明示
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
    """1 疾病分の 3 パネル (観測/平滑化/Scale BB 投影) ヒートマップを生成。"""
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
    """選んだ年齢バンドの実績 + 投影率の時系列を 1 枚にまとめた折れ線図。"""
    fit = fit_scale_bb(rates, ages=ages, years=years, config=config)
    fit = project_scale_bb(fit)

    fig, ax = plt.subplots(figsize=(11, 6), constrained_layout=True)
    for a in ages_to_plot:
        if a not in ages:
            # 最も近い年齢を採用
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
        description="Scale BB スタイルの改善率ヒートマップ可視化"
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
        help="mortality 時の disease_id (デフォルト cancer heart_disease cerebrovascular)",
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
        help="出力ディレクトリ (default: figures/)",
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
