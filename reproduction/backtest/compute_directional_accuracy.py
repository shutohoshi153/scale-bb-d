"""Directional accuracy: did the method predict the correct sign of change
relative to the observed rate at the training cutoff?

For each (disease, sex, age, year):
  actual_change    = actual_rate    - rate_at_cutoff
  predicted_change = predicted_rate - rate_at_cutoff
  match = sign(actual_change) == sign(predicted_change), excluding cells
          where sign(actual_change) == 0 (ambiguous truth).

Cells where the method predicts no change (sign(predicted_change) == 0,
e.g. naive_last by construction) count as a miss — that is the point: such
methods carry no directional signal.

[ADD 2026-09-02] Two reference baselines and two uncertainty measures (paper §6.3):
  always_down       predicted_change ≡ −1  → DA equals the share of cells whose
                    actual change is negative (majority-direction benchmark)
  sign_last_change  continue the sign of the last observed raw change
                    m(x, y_c) − m(x, y_prev)  (the naive practitioner rule)
  pt_pvalue         Pesaran–Timmermann (1992) sign-predictability test; NaN when
                    the prediction is constant across cells (test degenerate)
  ci_lo / ci_hi     95% block-bootstrap interval for DA, resampling age groups
                    (each age keeps all its validation years → serial
                    dependence within an age series is preserved)

Outputs (under output/directional/):
  tables/directional_long.csv             cell-level rows with match flag
  tables/directional_summary.csv          per (cutoff, method, disease, sex)
  tables/directional_summary_total.csv    same, sex=total only (wide-friendly)
  figures/scalebb_directional_per_cutoff.png   bar: ScaleBB per disease × cutoff
  figures/method_directional_comparison.png    grouped bar: 4 methods × disease, 3 panels
  figures/scalebb_vs_loglin_directional.png    head-to-head ScaleBB vs loglin_trend
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# [REPRO] パスは自己完結パス層に集約 (元: ROOT=parents[2] からの相対参照)
import _paths

BASE = _paths.OUTPUT_DIR  # 元: ROOT/"BackTest_ScaleBB_2015_2024"/"output"
OUT = BASE / "directional"
(OUT / "tables").mkdir(parents=True, exist_ok=True)
(OUT / "figures").mkdir(parents=True, exist_ok=True)

CUTOFFS = [
    (2014, None,           "train ≤2014 → 2015-2024"),
    (2021, "cutoff_2021",  "train ≤2021 → 2022-2024"),
    (2022, "cutoff_2022",  "train ≤2022 → 2023-2024"),
]


def _base_dir(subdir: str | None) -> Path:
    return BASE / subdir if subdir else BASE


def load_observed_at_cutoff(subdir: str | None, cutoff: int) -> pd.DataFrame:
    fit = pd.read_csv(_base_dir(subdir) / "tables" / "fit_long.csv")
    o = fit[(fit["kind"] == "observed_train") & (fit["year"] == cutoff)].copy()
    return o[["disease", "sex", "age_low", "rate_per_100k"]].rename(
        columns={"rate_per_100k": "rate_at_cutoff"}
    )


def load_prev_observed(subdir: str | None, cutoff: int) -> pd.DataFrame:
    """観測終端の 1 つ前の観測年の率 (sign_last_change 用)."""
    fit = pd.read_csv(_base_dir(subdir) / "tables" / "fit_long.csv")
    o = fit[(fit["kind"] == "observed_train") & (fit["year"] < cutoff)
            & fit["rate_per_100k"].notna()]
    last = o.groupby(["disease", "sex", "age_low"])["year"].transform("max")
    o = o[o["year"] == last]
    return o[["disease", "sex", "age_low", "rate_per_100k"]].rename(
        columns={"rate_per_100k": "rate_prev"})


def pesaran_timmermann(actual_sign: np.ndarray, pred_sign: np.ndarray) -> float:
    """Pesaran & Timmermann (1992) の符号予測検定の片側 p 値.
    予測が一定 (Pz∈{0,1}) の場合は分散がゼロになり検定が定義できないため NaN を返す."""
    from scipy.stats import norm
    y = (actual_sign > 0).astype(float); z = (pred_sign > 0).astype(float)
    n = y.size
    if n == 0:
        return np.nan
    p = float((y == z).mean()); py = float(y.mean()); pz = float(z.mean())
    if pz in (0.0, 1.0) or py in (0.0, 1.0):
        return np.nan
    p_star = py * pz + (1 - py) * (1 - pz)
    var_p = p_star * (1 - p_star) / n
    var_pstar = ((2 * py - 1) ** 2 * pz * (1 - pz) + (2 * pz - 1) ** 2 * py * (1 - py)
                 + 4 * py * pz * (1 - py) * (1 - pz) / n) / n
    denom = var_p - var_pstar
    if denom <= 0:
        return np.nan
    stat = (p - p_star) / np.sqrt(denom)
    return float(1 - norm.cdf(stat))


def block_bootstrap_ci(g: pd.DataFrame, n_boot: int = 2000, seed: int = 20260902) -> tuple[float, float]:
    """年齢群をブロックとして復元抽出し DA の 95% 区間を返す (各年齢は全検証年を保持)."""
    rng = np.random.default_rng(seed)
    ages = g["age_low"].unique()
    by_age = {a: (int(sub["match"].sum()), int(len(sub))) for a, sub in g.groupby("age_low")}
    vals = []
    for _ in range(n_boot):
        pick = rng.choice(ages, size=ages.size, replace=True)
        hit = sum(by_age[a][0] for a in pick); tot = sum(by_age[a][1] for a in pick)
        vals.append(hit / tot * 100 if tot else np.nan)
    return float(np.nanpercentile(vals, 2.5)), float(np.nanpercentile(vals, 97.5))


def load_val(subdir: str | None) -> pd.DataFrame:
    sb = pd.read_csv(_base_dir(subdir) / "tables" / "validation_long.csv")
    sb = sb[["disease", "sex", "age_low", "year",
             "actual_rate_per_100k", "predicted_rate_per_100k"]].copy()
    sb["method"] = "scalebb"

    base = pd.read_csv(_base_dir(subdir) / "tables" / "validation_long_baseline.csv")
    base = base[["method", "disease", "sex", "age_low", "year",
                 "actual_rate_per_100k", "predicted_rate_per_100k"]].copy()

    return pd.concat([sb, base], ignore_index=True)


def compute_directional(cutoff: int, subdir: str | None) -> pd.DataFrame:
    obs = load_observed_at_cutoff(subdir, cutoff)
    val = load_val(subdir)
    df = val.merge(obs, on=["disease", "sex", "age_low"], how="left")
    # [ADD 2026-09-02] reference baselines built from the training data only
    prev = load_prev_observed(subdir, cutoff)
    ref_base = df[df["method"] == "scalebb"].drop(columns=["method"]).merge(
        prev, on=["disease", "sex", "age_low"], how="left")
    ad = ref_base.copy(); ad["method"] = "always_down"
    ad["predicted_rate_per_100k"] = ad["rate_at_cutoff"] * (1.0 - 1e-9)
    sl = ref_base.copy(); sl["method"] = "sign_last_change"
    sl["predicted_rate_per_100k"] = sl["rate_at_cutoff"] + (sl["rate_at_cutoff"] - sl["rate_prev"])
    # [ADD 2026-09-03] majority_direction: 検証窓で多数派だった方向を全セルで答える規則 (真の多数派基準)。
    # always_down は改善系列でのみ多数派基準になる (ショック期の窓では少数派方向になる) ため、
    # 窓ごとに多数派方向を判定する規則を別に置く。事後的な (oracle) 基準であり、chance level の定義に使う。
    md = ref_base.copy(); md["method"] = "majority_direction"
    _chg = np.sign(md["actual_rate_per_100k"] - md["rate_at_cutoff"])
    _maj = (_chg.where(_chg != 0).groupby([md["disease"], md["sex"]]).transform(
        lambda v: 1.0 if (v > 0).sum() > (v < 0).sum() else -1.0))
    # [FIX 2026-09-30] 加法的な微小量で方向を与える。旧実装は rate_at_cutoff × (1 ± 1e-9) で、cutoff 年の率が 0 の
    # セルでは予測変化が 0 (方向なし) になり、多数派方向が「上昇」でも不一致に数えられていた。そのため
    # majority_direction の DA が多数派方向比率 (majority_pct) を下回っていた (若年の率 0 を含む kidney・diabetes 等)。
    md["predicted_rate_per_100k"] = md["rate_at_cutoff"] + 1e-9 * _maj
    cols = list(df.columns)
    df = pd.concat([df, ad[cols], sl[cols], md[cols]], ignore_index=True)
    df["actual_change"] = df["actual_rate_per_100k"] - df["rate_at_cutoff"]
    df["predicted_change"] = df["predicted_rate_per_100k"] - df["rate_at_cutoff"]
    df = df.dropna(subset=["actual_change", "predicted_change", "rate_at_cutoff"])
    # [CHG 2026-09-30] cutoff 年の観測率が 0 以下のセルは評価しない (再審査 A-5)。Scale BB-D はその年齢で
    # 平滑化率から投影を始める (model.select_base_rates) ため、観測率 0 を基準にした方向は投影の方向
    # (末端改善率の符号) を表さない。残るセルでは投影の起点と DA の基準水準が一致する。
    df = df[df["rate_at_cutoff"] > 0]
    df["actual_sign"] = np.sign(df["actual_change"])
    df["pred_sign"] = np.sign(df["predicted_change"])
    df["match"] = (df["actual_sign"] == df["pred_sign"]) & (df["actual_sign"] != 0)
    df["evaluable"] = df["actual_sign"] != 0  # exclude ambiguous-truth cells
    df["cutoff"] = cutoff
    return df


def summarize(long_df: pd.DataFrame) -> pd.DataFrame:
    evl = long_df[long_df["evaluable"]]
    grp = evl.groupby(["cutoff", "method", "disease", "sex"])
    rows = []
    for (cutoff, method, disease, sex), g in grp:
        n = len(g)
        matches = int(g["match"].sum())
        # share of predictions that are "no change" (signal-less)
        n_flat = int((g["pred_sign"] == 0).sum())
        down_share = float((g["actual_sign"] < 0).mean() * 100) if n else np.nan
        row = {
            "cutoff": cutoff, "method": method, "disease": disease, "sex": sex,
            "n_cells_evaluable": n,
            "n_matches": matches,
            "dir_acc_pct": round(matches / n * 100, 2) if n else np.nan,
            "n_flat_preds": n_flat,
            "flat_pred_pct": round(n_flat / n * 100, 2) if n else np.nan,
            # [ADD 2026-09-02]
            "majority_pct": round(max(down_share, 100 - down_share), 2) if n else np.nan,
            "pred_down_pct": round(float((g["pred_sign"] < 0).mean() * 100), 2) if n else np.nan,
            "pt_pvalue": round(pesaran_timmermann(g["actual_sign"].to_numpy(), g["pred_sign"].to_numpy()), 4),
        }
        if method in ("scalebb", "loglin_trend") and sex == "total":
            lo, hi = block_bootstrap_ci(g)
            row["ci_lo"], row["ci_hi"] = round(lo, 2), round(hi, 2)
        else:
            row["ci_lo"], row["ci_hi"] = np.nan, np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    all_long = []
    for cutoff, subdir, _ in CUTOFFS:
        long_df = compute_directional(cutoff, subdir)
        all_long.append(long_df)
    long_all = pd.concat(all_long, ignore_index=True)
    long_all.to_csv(OUT / "tables" / "directional_long.csv", index=False)
    print(f"wrote directional_long.csv ({len(long_all):,} rows)")

    summary = summarize(long_all)
    summary = summary.sort_values(["cutoff", "method", "disease", "sex"]).reset_index(drop=True)
    summary.to_csv(OUT / "tables" / "directional_summary.csv", index=False)
    print(f"wrote directional_summary.csv ({len(summary)} rows)")

    summary_total = summary[summary["sex"] == "total"].copy()
    summary_total.to_csv(OUT / "tables" / "directional_summary_total.csv", index=False)

    # [ADD 2026-09-03] 表 6.3: Scale BB-D の勝敗 (8 疾病 × 3 cutoff = 24 比較, sex=total) を機械生成
    sbda = summary_total[summary_total["method"] == "scalebb"].set_index(["cutoff", "disease"])["dir_acc_pct"]
    wl_rows = []
    for m in ["naive_last", "mean_3pts", "loglin_trend", "always_down", "majority_direction", "sign_last_change"]:
        other = summary_total[summary_total["method"] == m].set_index(["cutoff", "disease"])["dir_acc_pct"]
        j = pd.concat([sbda.rename("sb"), other.rename("o")], axis=1).dropna()
        wl_rows.append({"vs": m, "n": len(j), "wins": int((j["sb"] > j["o"] + 1e-9).sum()),
                        "ties": int((abs(j["sb"] - j["o"]) <= 1e-9).sum()),
                        "losses": int((j["sb"] < j["o"] - 1e-9).sum())})
    pd.DataFrame(wl_rows).to_csv(OUT / "tables" / "directional_winloss.csv", index=False)
    print("wrote directional_winloss.csv")

    # ---------- Plot 1: ScaleBB directional accuracy per cutoff ----------
    sb = summary_total[summary_total["method"] == "scalebb"].copy()
    diseases = sorted(sb["disease"].unique())
    x = np.arange(len(diseases))
    w = 0.25
    fig, ax = plt.subplots(figsize=(11, 5.5))
    colors = ["#d62728", "#ff7f0e", "#2ca02c"]
    for k, (cutoff, _, title) in enumerate(CUTOFFS):
        vals = []
        for d in diseases:
            row = sb[(sb["cutoff"] == cutoff) & (sb["disease"] == d)]
            vals.append(row["dir_acc_pct"].iloc[0] if not row.empty else 0)
        ax.bar(x + (k - 1) * w, vals, width=w, color=colors[k], label=title)
        # [ADD 2026-09-02] majority-direction share per disease (the relevant chance level)
        maj = []
        for d in diseases:
            row = sb[(sb["cutoff"] == cutoff) & (sb["disease"] == d)]
            maj.append(row["majority_pct"].iloc[0] if not row.empty else np.nan)
        ax.scatter(x + (k - 1) * w, maj, marker="_", s=260, color="black", zorder=3,
                   label="majority-direction share" if k == 0 else None)
    ax.axhline(50, color="grey", lw=0.6, ls=":", alpha=0.5, label="50%")
    ax.set_xticks(x)
    ax.set_xticklabels(diseases, rotation=20, ha="right")
    ax.set_ylabel("Directional accuracy %  (higher = better)")
    ax.set_ylim(0, 100)
    ax.set_title("ScaleBB directional accuracy by training cutoff (sex=total)")
    ax.grid(axis="y", alpha=0.3)
    ax.legend(fontsize=9, loc="lower left")
    fig.tight_layout()
    out1 = OUT / "figures" / "scalebb_directional_per_cutoff.png"
    fig.savefig(out1, dpi=120)
    plt.close(fig)
    print(f"wrote {out1.name}")

    # ---------- Plot 2: 4 methods × 8 diseases × 3 cutoffs (3 panels) ----------
    methods = ["scalebb", "naive_last", "mean_3pts", "loglin_trend"]
    cmap = {"scalebb": "#2ca02c", "naive_last": "#1f77b4",
            "mean_3pts": "#ff7f0e", "loglin_trend": "#d62728"}
    fig, axes = plt.subplots(1, 3, figsize=(20, 5.5), sharey=True)
    for ax, (cutoff, _, title) in zip(axes, CUTOFFS):
        x = np.arange(len(diseases))
        w = 0.2
        for k, m in enumerate(methods):
            vals = []
            for d in diseases:
                row = summary_total[(summary_total["cutoff"] == cutoff)
                                    & (summary_total["disease"] == d)
                                    & (summary_total["method"] == m)]
                vals.append(row["dir_acc_pct"].iloc[0] if not row.empty else 0)
            ax.bar(x + (k - 1.5) * w, vals, width=w, color=cmap[m], label=m)
        ax.axhline(50, color="grey", lw=0.8, ls="--", alpha=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels(diseases, rotation=25, ha="right")
        ax.set_title(title)
        ax.set_ylabel("Directional accuracy %")
        ax.set_ylim(0, 100)
        ax.grid(axis="y", alpha=0.3)
    axes[0].legend(fontsize=9, loc="lower left")
    fig.suptitle(
        "Directional accuracy by method × disease × training cutoff (sex=total)\n"
        "naive_last predicts no change (pred_sign=0) by construction → directional accuracy = 0%",
        fontsize=11,
    )
    fig.tight_layout()
    out2 = OUT / "figures" / "method_directional_comparison.png"
    fig.savefig(out2, dpi=120)
    plt.close(fig)
    print(f"wrote {out2.name}")

    # ---------- Plot 3: head-to-head ScaleBB vs loglin_trend ----------
    # loglin_trend is the strongest baseline w/ explicit directional signal;
    # naive_last/mean_3pts have weak/no signal so a fair comparison is vs loglin.
    fig, axes = plt.subplots(1, 3, figsize=(20, 5.5), sharey=True)
    for ax, (cutoff, _, title) in zip(axes, CUTOFFS):
        x = np.arange(len(diseases))
        w = 0.4
        sb_vals, ll_vals = [], []
        for d in diseases:
            sb_row = summary_total[(summary_total["cutoff"] == cutoff)
                                   & (summary_total["disease"] == d)
                                   & (summary_total["method"] == "scalebb")]
            ll_row = summary_total[(summary_total["cutoff"] == cutoff)
                                   & (summary_total["disease"] == d)
                                   & (summary_total["method"] == "loglin_trend")]
            sb_vals.append(sb_row["dir_acc_pct"].iloc[0] if not sb_row.empty else 0)
            ll_vals.append(ll_row["dir_acc_pct"].iloc[0] if not ll_row.empty else 0)
        ax.bar(x - w / 2, sb_vals, width=w, color=cmap["scalebb"], label="scalebb")
        ax.bar(x + w / 2, ll_vals, width=w, color=cmap["loglin_trend"], label="loglin_trend")
        maj = [summary_total[(summary_total["cutoff"] == cutoff) & (summary_total["disease"] == d)
                             & (summary_total["method"] == "scalebb")]["majority_pct"].iloc[0]
               for d in diseases]
        ax.scatter(x, maj, marker="_", s=420, color="black", zorder=3, label="majority-direction share")
        ax.axhline(50, color="grey", lw=0.6, ls=":", alpha=0.5)
        ax.set_xticks(x)
        ax.set_xticklabels(diseases, rotation=25, ha="right")
        ax.set_title(title)
        ax.set_ylabel("Directional accuracy %")
        ax.set_ylim(0, 100)
        ax.grid(axis="y", alpha=0.3)
    axes[0].legend(fontsize=10, loc="lower left")
    fig.suptitle(
        "ScaleBB vs loglin_trend — directional accuracy head-to-head (sex=total)",
        fontsize=12,
    )
    fig.tight_layout()
    out3 = OUT / "figures" / "scalebb_vs_loglin_directional.png"
    fig.savefig(out3, dpi=120)
    plt.close(fig)
    print(f"wrote {out3.name}")

    # ---------- Print summary table ----------
    print()
    print("=== Directional accuracy (sex=total, all cutoffs) ===")
    pv = summary_total.pivot_table(
        index=["disease"], columns=["cutoff", "method"],
        values="dir_acc_pct", aggfunc="first",
    )
    print(pv.to_string())


if __name__ == "__main__":
    main()
